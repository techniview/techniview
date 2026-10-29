"""Personalized, deterministic practice recommendations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import exp2

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.errors import ApiError
from ..models import (
    CurriculumNode,
    Difficulty,
    Problem,
    ProblemState,
    ProblemTagKind,
    Submission,
    SubmissionStatus,
    User,
    UserRole,
)
from .curriculum import (
    TECHNIQUE_POOLS,
    _technique_memberships,
    technique_pool_metadata,
)
from .presentation import problem_summary

MAX_RECOMMENDATIONS = 3
MIN_POOL_ATTEMPTS = 3
RECENT_FAILURE_WINDOW = timedelta(days=30)
# Each attempt's pass-rate weight halves for every 30 days of age.
PASS_RATE_HALF_LIFE_DAYS = 30
SAMPLE_STATUSES = (
    SubmissionStatus.PASSED,
    SubmissionStatus.FAILED,
    SubmissionStatus.COMPILE_ERROR,
    SubmissionStatus.RUNTIME_ERROR,
    SubmissionStatus.TIMEOUT,
    SubmissionStatus.RESOURCE_LIMIT,
)


@dataclass(frozen=True)
class AttemptStats:
    attempts: int = 0
    passes: int = 0
    failures: int = 0
    weighted_attempts: float = 0.0
    weighted_passes: float = 0.0
    last_attempt_at: datetime | None = None
    last_failure_at: datetime | None = None

    @property
    def pass_rate(self) -> float:
        # Beta(1, 1) smoothing is applied after 30-day half-life weighting.
        return (self.weighted_passes + 1) / (self.weighted_attempts + 2)


@dataclass(frozen=True)
class Candidate:
    problem: Problem
    priority: int
    stats: AttemptStats


def _aggregate_attempts(rows, now: datetime) -> dict[int, AttemptStats]:
    totals: dict[int, dict] = defaultdict(
        lambda: {
            "attempts": 0,
            "passes": 0,
            "failures": 0,
            "weighted_attempts": 0.0,
            "weighted_passes": 0.0,
            "last_attempt_at": None,
            "last_failure_at": None,
        }
    )
    for row in rows:
        values = totals[row.problem_id]
        completed_at = row.completed_at
        age_days = max(0.0, (now - completed_at).total_seconds() / 86_400)
        weight = exp2(-age_days / PASS_RATE_HALF_LIFE_DAYS)
        values["attempts"] += 1
        values["weighted_attempts"] += weight
        if row.status == SubmissionStatus.PASSED:
            values["passes"] += 1
            values["weighted_passes"] += weight
        else:
            values["failures"] += 1
            last_failure = values["last_failure_at"]
            if last_failure is None or completed_at > last_failure:
                values["last_failure_at"] = completed_at
        last_attempt = values["last_attempt_at"]
        if last_attempt is None or completed_at > last_attempt:
            values["last_attempt_at"] = completed_at
    return {problem_id: AttemptStats(**values) for problem_id, values in totals.items()}


def _pool_order() -> dict[str, int]:
    return {slug: index for index, (slug, *_rest) in enumerate(TECHNIQUE_POOLS)}


def _candidate_sort_key(candidate: Candidate) -> tuple:
    difficulty_order = {
        Difficulty.EASY: 0,
        Difficulty.MEDIUM: 1,
        Difficulty.HARD: 2,
    }
    return (
        difficulty_order[candidate.problem.difficulty],
        candidate.priority,
        candidate.problem.title.casefold(),
        candidate.problem.id,
    )


def _select_ranked(
    pools: dict[str, dict],
    candidates_by_pool: dict[str, list[Candidate]],
    completed_counts: dict[str, int],
    pool_attempts: dict[str, int],
    pool_weighted_attempts: dict[str, float],
    pool_weighted_passes: dict[str, float],
    now: datetime,
) -> list[dict]:
    pool_order = _pool_order()
    ready = {
        slug: metadata
        for slug, metadata in pools.items()
        if candidates_by_pool.get(slug)
        and all(
            completed_counts.get(prerequisite, 0) > 0
            for prerequisite in metadata["prerequisite_pool_slugs"]
        )
    }
    selected: list[dict] = []
    selected_pools: set[str] = set()

    def append(slug: str, candidate: Candidate, reason: str) -> None:
        selected_pools.add(slug)
        selected.append(
            {
                "rank": len(selected) + 1,
                "reason": reason,
                "pool_slug": slug,
                "pool_name": pools[slug]["name"],
                "problem": problem_summary(candidate.problem),
            }
        )

    # Recovery is allowed in an earlier pool, but never before its own
    # prerequisites are met. Prefer the most recently failed candidate in the
    # weakest pool with enough history to make its rate useful.
    untouched_ready = [
        metadata
        for slug, metadata in ready.items()
        if completed_counts.get(slug, 0) == 0
    ]
    frontier = untouched_ready or list(ready.values())
    next_tier = min(
        (metadata["tier"] for metadata in frontier if metadata["tier"] is not None),
        default=999,
    )
    recovery_pools = []
    for slug in ready:
        items = candidates_by_pool[slug]
        tier = ready[slug]["tier"] if ready[slug]["tier"] is not None else 999
        if tier > next_tier:
            continue
        attempts = pool_attempts.get(slug, 0)
        if attempts < MIN_POOL_ATTEMPTS:
            continue
        recent_failed = [
            item
            for item in items
            if item.stats.last_failure_at is not None
            and item.stats.last_failure_at >= now - RECENT_FAILURE_WINDOW
        ]
        if not recent_failed:
            continue
        weighted_attempts = pool_weighted_attempts.get(slug, 0.0)
        weighted_passes = pool_weighted_passes.get(slug, 0.0)
        pool_rate = (weighted_passes + 1) / (weighted_attempts + 2)
        last_failure = max(item.stats.last_failure_at for item in recent_failed)
        recovery_pools.append(
            (
                pool_rate,
                -last_failure.timestamp(),
                pool_order.get(slug, 999),
                slug,
                recent_failed,
            )
        )
    if recovery_pools:
        _rate, _recent, _order, slug, recent_failed = min(recovery_pools)
        candidate = min(
            recent_failed,
            key=lambda item: (
                -item.stats.last_failure_at.timestamp(),
                -item.stats.failures,
                *_candidate_sort_key(item),
            ),
        )
        append(slug, candidate, "struggling_area")

    # Continue through the earliest reachable core tier before moving ahead.
    # Optional extensions follow core pools when no core candidate remains.
    available = [slug for slug in ready if slug not in selected_pools]
    if available and len(selected) < MAX_RECOMMENDATIONS:
        untouched = [slug for slug in available if completed_counts.get(slug, 0) == 0]
        progression_candidates = untouched or available
        slug = min(
            progression_candidates,
            key=lambda item: (
                pools[item]["tier"] if pools[item]["tier"] is not None else 999,
                pool_order.get(item, 999),
            ),
        )
        candidate = min(candidates_by_pool[slug], key=_candidate_sort_key)
        append(slug, candidate, "next_trail_step")

    # Spread the final slot to the least-covered ready pool.
    available = [slug for slug in ready if slug not in selected_pools]
    if available and len(selected) < MAX_RECOMMENDATIONS:

        def coverage_key(slug: str) -> tuple:
            total = len(candidates_by_pool[slug]) + completed_counts.get(slug, 0)
            coverage = completed_counts.get(slug, 0) / total if total else 0.0
            tier = pools[slug]["tier"] if pools[slug]["tier"] is not None else 999
            return coverage, tier, pool_order.get(slug, 999)

        slug = min(available, key=coverage_key)
        candidate = min(candidates_by_pool[slug], key=_candidate_sort_key)
        append(slug, candidate, "low_completion_coverage")

    return selected


def get_recommendations(db: Session, user: User) -> list[dict]:
    """Return up to three personalized curriculum recommendations for a student."""
    if user.role != UserRole.STUDENT:
        raise ApiError(403, "student_required", "Student access is required.")

    nodes = list(
        db.scalars(
            select(CurriculumNode)
            .join(Problem, Problem.id == CurriculumNode.problem_id)
            .options(selectinload(CurriculumNode.problem).selectinload(Problem.tags))
            .where(
                Problem.owner_id.is_(None),
                Problem.state == ProblemState.PUBLISHED,
            )
            .order_by(CurriculumNode.priority)
        ).all()
    )
    if not nodes:
        return []

    problem_ids = [node.problem_id for node in nodes]
    now = datetime.now(UTC).replace(tzinfo=None)
    raw_attempts = db.execute(
        select(Submission.problem_id, Submission.status, Submission.completed_at).where(
            Submission.student_id == user.id,
            Submission.problem_id.in_(problem_ids),
            Submission.is_practice_run.is_(False),
            Submission.completed_at.is_not(None),
            Submission.status.in_(SAMPLE_STATUSES),
            or_(
                Submission.is_late.is_(False),
                Submission.late_approved_at.is_not(None),
            ),
        )
    ).all()
    stats_by_problem = _aggregate_attempts(raw_attempts, now)

    pools = {pool["slug"]: pool for pool in technique_pool_metadata()}
    candidates_by_pool: dict[str, list[Candidate]] = defaultdict(list)
    completed_counts: dict[str, int] = defaultdict(int)
    pool_attempts: dict[str, int] = defaultdict(int)
    pool_weighted_attempts: dict[str, float] = defaultdict(float)
    pool_weighted_passes: dict[str, float] = defaultdict(float)
    for node in nodes:
        problem = node.problem
        stats = stats_by_problem.get(problem.id, AttemptStats())
        memberships = _technique_memberships(
            tag for tag in problem.tags if tag.kind == ProblemTagKind.TECHNIQUE
        )
        for slug in memberships:
            if slug not in pools:
                continue
            pool_attempts[slug] += stats.attempts
            pool_weighted_attempts[slug] += stats.weighted_attempts
            pool_weighted_passes[slug] += stats.weighted_passes
            if stats.passes:
                completed_counts[slug] += 1
            else:
                candidates_by_pool[slug].append(
                    Candidate(problem=problem, priority=node.priority, stats=stats)
                )

    return _select_ranked(
        pools,
        candidates_by_pool,
        completed_counts,
        pool_attempts,
        pool_weighted_attempts,
        pool_weighted_passes,
        now,
    )
