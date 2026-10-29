from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.errors import ApiError
from app.models import (
    Assignment,
    AssignmentItem,
    Difficulty,
    ErrorCategory,
    Problem,
    Submission,
    SubmissionStatus,
    User,
    UserRole,
)
from app.services.curriculum import technique_pool_metadata
from app.services.recommendations import (
    AttemptStats,
    Candidate,
    _aggregate_attempts,
    _select_ranked,
    get_recommendations,
)
from sqlalchemy import select


def _fake_candidate(
    problem_id: int, title: str, attempts: AttemptStats | None = None
) -> Candidate:
    attempts = attempts or AttemptStats()
    return Candidate(
        problem=SimpleNamespace(
            id=problem_id,
            title=title,
            difficulty=Difficulty.EASY,
            origin="imported",
            state="published",
            tags=[],
            source_category=None,
        ),
        priority=problem_id,
        stats=attempts,
    )


def _pool(slug: str) -> dict:
    return next(pool for pool in technique_pool_metadata() if pool["slug"] == slug)


def test_suggestion_slots_follow_trail_and_spread_pools():
    pools = {
        slug: _pool(slug) for slug in ("arrays-and-hashing", "two-pointers", "stack")
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    candidates = {
        "arrays-and-hashing": [],
        "two-pointers": [_fake_candidate(2, "Two pointers")],
        "stack": [_fake_candidate(3, "Stack")],
    }
    result = _select_ranked(
        pools,
        candidates,
        {"arrays-and-hashing": 1},
        {},
        {},
        {},
        now,
    )
    assert [item["reason"] for item in result] == [
        "next_trail_step",
        "low_completion_coverage",
    ]
    assert [item["pool_slug"] for item in result] == [
        "two-pointers",
        "stack",
    ]
    assert len({item["pool_slug"] for item in result}) == len(result)


def test_progression_advances_to_untouched_ready_tier_after_foundation_pass():
    pools = {
        slug: _pool(slug) for slug in ("arrays-and-hashing", "two-pointers", "stack")
    }
    candidates = {
        "arrays-and-hashing": [_fake_candidate(1, "Foundation follow-up")],
        "two-pointers": [_fake_candidate(2, "Next Trail step")],
        "stack": [_fake_candidate(3, "Parallel next step")],
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    advanced = _select_ranked(
        pools,
        candidates,
        {"arrays-and-hashing": 1},
        {},
        {},
        {},
        now,
    )
    assert advanced[0]["reason"] == "next_trail_step"
    assert advanced[0]["pool_slug"] == "two-pointers"

    fallback = _select_ranked(
        pools,
        candidates,
        {
            "arrays-and-hashing": 1,
            "two-pointers": 1,
            "stack": 1,
        },
        {},
        {},
        {},
        now,
    )
    assert fallback[0]["reason"] == "next_trail_step"
    assert fallback[0]["pool_slug"] == "arrays-and-hashing"


def test_recovery_uses_lowest_smoothed_pass_rate_and_recent_failure():
    pools = {
        slug: _pool(slug) for slug in ("arrays-and-hashing", "two-pointers", "stack")
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    candidates = {
        "arrays-and-hashing": [],
        "two-pointers": [
            _fake_candidate(
                1,
                "Mostly passing",
                AttemptStats(
                    attempts=4,
                    passes=3,
                    failures=1,
                    weighted_attempts=4,
                    weighted_passes=3,
                    last_failure_at=now - timedelta(days=1),
                ),
            )
        ],
        "stack": [
            _fake_candidate(
                2,
                "Struggling",
                AttemptStats(
                    attempts=4,
                    passes=0,
                    failures=4,
                    weighted_attempts=4,
                    weighted_passes=0,
                    last_failure_at=now - timedelta(hours=1),
                ),
            )
        ],
    }
    result = _select_ranked(
        pools,
        candidates,
        {"arrays-and-hashing": 1},
        {"two-pointers": 4, "stack": 4},
        {"two-pointers": 4, "stack": 4},
        {"two-pointers": 3, "stack": 0},
        now,
    )
    assert result[0]["reason"] == "struggling_area"
    assert result[0]["pool_slug"] == "stack"


def test_sparse_attempts_and_stale_failures_do_not_create_recovery():
    pools = {"arrays-and-hashing": _pool("arrays-and-hashing")}
    now = datetime.now(UTC).replace(tzinfo=None)
    sparse = _fake_candidate(
        1,
        "Sparse",
        AttemptStats(
            attempts=2,
            failures=2,
            last_failure_at=now - timedelta(days=1),
        ),
    )
    stale = _fake_candidate(
        2,
        "Stale",
        AttemptStats(
            attempts=4,
            failures=4,
            last_failure_at=now - timedelta(days=31),
        ),
    )
    assert _select_ranked(pools, {}, {}, {}, {}, {}, now) == []
    result = _select_ranked(
        pools,
        {"arrays-and-hashing": [sparse, stale]},
        {},
        {"arrays-and-hashing": 2},
        {"arrays-and-hashing": 2.0},
        {},
        now,
    )
    assert result[0]["reason"] == "next_trail_step"


def test_recovery_does_not_jump_ahead_of_next_trail_tier():
    pools = {
        slug: _pool(slug)
        for slug in ("arrays-and-hashing", "two-pointers", "binary-search")
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    future_struggle = _fake_candidate(
        3,
        "Future tier",
        AttemptStats(
            attempts=4,
            failures=4,
            weighted_attempts=4,
            last_failure_at=now - timedelta(hours=1),
        ),
    )
    result = _select_ranked(
        pools,
        {
            "arrays-and-hashing": [],
            "two-pointers": [_fake_candidate(2, "Next tier")],
            "binary-search": [future_struggle],
        },
        {"arrays-and-hashing": 1},
        {"binary-search": 4},
        {"binary-search": 4.0},
        {},
        now,
    )
    assert result[0]["pool_slug"] == "two-pointers"
    assert result[0]["reason"] == "next_trail_step"


def test_recovery_frontier_moves_to_next_untouched_tier():
    pools = {
        slug: _pool(slug)
        for slug in ("arrays-and-hashing", "two-pointers", "binary-search")
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    candidates = {
        "arrays-and-hashing": [_fake_candidate(1, "Foundation follow-up")],
        "two-pointers": [
            _fake_candidate(
                2,
                "Tier 2 struggle",
                AttemptStats(
                    attempts=4,
                    failures=3,
                    weighted_attempts=4,
                    weighted_passes=1,
                    last_failure_at=now - timedelta(hours=1),
                ),
            )
        ],
        "binary-search": [
            _fake_candidate(
                3,
                "Tier 3 struggle",
                AttemptStats(
                    attempts=4,
                    failures=4,
                    weighted_attempts=4,
                    weighted_passes=0,
                    last_failure_at=now - timedelta(minutes=30),
                ),
            )
        ],
    }
    result = _select_ranked(
        pools,
        candidates,
        {"arrays-and-hashing": 1},
        {"two-pointers": 4, "binary-search": 4},
        {"two-pointers": 4.0, "binary-search": 4.0},
        {"two-pointers": 1.0, "binary-search": 0.0},
        now,
    )
    assert result[0]["reason"] == "struggling_area"
    assert result[0]["pool_slug"] == "two-pointers"


def test_recency_weighting_can_change_recovery_ranking():
    pools = {
        slug: _pool(slug) for slug in ("arrays-and-hashing", "two-pointers", "stack")
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = (
        [
            SimpleNamespace(
                problem_id=2,
                status=SubmissionStatus.PASSED,
                completed_at=now - timedelta(days=90),
            )
            for _ in range(3)
        ]
        + [
            SimpleNamespace(
                problem_id=2,
                status=SubmissionStatus.FAILED,
                completed_at=now - timedelta(days=1),
            )
        ]
        + [
            SimpleNamespace(
                problem_id=3,
                status=status,
                completed_at=now - timedelta(days=1),
            )
            for status in (
                SubmissionStatus.PASSED,
                SubmissionStatus.PASSED,
                SubmissionStatus.FAILED,
                SubmissionStatus.FAILED,
            )
        ]
    )
    stats = _aggregate_attempts(rows, now)
    candidates = {
        "arrays-and-hashing": [],
        "two-pointers": [_fake_candidate(2, "Old passes", stats[2])],
        "stack": [_fake_candidate(3, "Recent mixed results", stats[3])],
    }
    pool_attempts = {
        slug: stats[problem_id].attempts
        for slug, problem_id in (("two-pointers", 2), ("stack", 3))
    }
    pool_weighted_attempts = {
        slug: stats[problem_id].weighted_attempts
        for slug, problem_id in (("two-pointers", 2), ("stack", 3))
    }
    pool_weighted_passes = {
        slug: stats[problem_id].weighted_passes
        for slug, problem_id in (("two-pointers", 2), ("stack", 3))
    }
    # Without recency, Stack's smoothed pass rate is lower: 3/6 versus 4/6.
    assert (stats[3].passes + 1) / (stats[3].attempts + 2) < (
        (stats[2].passes + 1) / (stats[2].attempts + 2)
    )
    assert stats[2].pass_rate < stats[3].pass_rate
    result = _select_ranked(
        pools,
        candidates,
        {"arrays-and-hashing": 1},
        pool_attempts,
        pool_weighted_attempts,
        pool_weighted_passes,
        now,
    )
    assert result[0]["reason"] == "struggling_area"
    assert result[0]["pool_slug"] == "two-pointers"


def test_recommendations_use_own_practice_and_eligible_assignment_outcomes(
    db_session,
):
    student = db_session.scalar(
        select(User).where(User.email == "student@techniview.local")
    )
    problem = db_session.scalar(
        select(Problem).where(Problem.source_problem_id == "count-evens")
    )
    completed_problem = db_session.scalar(
        select(Problem).where(Problem.source_problem_id == "sum-list")
    )
    assignment = db_session.scalar(select(Assignment))
    completed_assignment_item = db_session.scalar(
        select(AssignmentItem).where(
            AssignmentItem.assignment_id == assignment.id,
            AssignmentItem.problem_id == completed_problem.id,
        )
    )
    if completed_assignment_item is None:
        completed_assignment_item = AssignmentItem(
            assignment_id=assignment.id,
            problem_id=completed_problem.id,
            item_order=100,
            points=Decimal("1"),
        )
        db_session.add(completed_assignment_item)
        db_session.flush()
    assignment_item = db_session.scalar(
        select(AssignmentItem).where(
            AssignmentItem.assignment_id == assignment.id,
            AssignmentItem.problem_id == problem.id,
        )
    )
    if assignment_item is None:
        last_item_order = db_session.scalar(
            select(AssignmentItem.item_order)
            .where(AssignmentItem.assignment_id == assignment.id)
            .order_by(AssignmentItem.item_order.desc())
            .limit(1)
        )
        assignment_item = AssignmentItem(
            assignment_id=assignment.id,
            problem_id=problem.id,
            item_order=last_item_order + 1,
            points=Decimal("1"),
        )
        db_session.add(assignment_item)
        db_session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    db_session.add_all(
        [
            Submission(
                student_id=student.id,
                problem_id=completed_problem.id,
                assignment_item_id=completed_assignment_item.id,
                status=SubmissionStatus.PASSED,
                score=Decimal("1"),
                source_code="approved late pass counts as completion",
                is_late=True,
                late_approved_at=now,
                completed_at=now,
            ),
            Submission(
                student_id=student.id,
                problem_id=problem.id,
                status=SubmissionStatus.PASSED,
                score=Decimal("1"),
                source_code="unapproved late pass is ignored",
                assignment_item_id=assignment_item.id,
                is_late=True,
                completed_at=now,
            ),
            Submission(
                student_id=student.id,
                problem_id=problem.id,
                status=SubmissionStatus.PASSED,
                score=Decimal("1"),
                source_code="debug run does not count as completion",
                is_practice_run=True,
                completed_at=now,
            ),
            Submission(
                student_id=student.id,
                problem_id=problem.id,
                status=SubmissionStatus.FAILED,
                primary_error=ErrorCategory.WRONG_ANSWER,
                source_code="source is never queried",
                completed_at=now - timedelta(minutes=2),
            ),
            Submission(
                student_id=student.id,
                problem_id=problem.id,
                status=SubmissionStatus.RUNTIME_ERROR,
                primary_error=ErrorCategory.RUNTIME_ERROR,
                source_code="source is never queried",
                assignment_item_id=assignment_item.id,
                completed_at=now - timedelta(minutes=1),
            ),
            Submission(
                student_id=student.id,
                problem_id=problem.id,
                status=SubmissionStatus.TIMEOUT,
                primary_error=ErrorCategory.TIMEOUT,
                source_code="source is never queried",
                completed_at=now,
            ),
            Submission(
                student_id=student.id,
                problem_id=problem.id,
                status=SubmissionStatus.INFRASTRUCTURE_ERROR,
                source_code="infrastructure is excluded",
                completed_at=now,
            ),
        ]
    )
    db_session.flush()

    items = get_recommendations(db_session, student)
    assert items[0]["reason"] == "struggling_area"
    assert items[0]["problem"]["id"] == problem.id
    assert items[0]["rank"] == 1
    assert [item["problem"]["id"] for item in items] == [problem.id]
    assert len(items) <= 3


def test_recommendations_are_student_only_and_isolated(db_session):
    teacher = db_session.scalar(
        select(User).where(User.email == "teacher@techniview.local")
    )
    with pytest.raises(ApiError) as error:
        get_recommendations(db_session, teacher)
    assert error.value.status_code == 403

    student = db_session.scalar(
        select(User).where(User.email == "student@techniview.local")
    )
    problem = db_session.scalar(
        select(Problem).where(Problem.source_problem_id == "count-evens")
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    db_session.add_all(
        [
            Submission(
                student_id=student.id,
                problem_id=problem.id,
                status=SubmissionStatus.FAILED,
                source_code="first student's own failure",
                completed_at=now - timedelta(minutes=i),
            )
            for i in range(3)
        ]
    )
    second_student = User(
        name="Other Student",
        email="other-student@example.test",
        password_hash="unused-in-direct-service-test",
        role=UserRole.STUDENT,
    )
    db_session.add(second_student)
    db_session.flush()
    student_recommendations = get_recommendations(db_session, student)
    other_recommendations = get_recommendations(db_session, second_student)
    assert all(item["reason"] != "struggling_area" for item in other_recommendations)
    assert student_recommendations[0]["reason"] == "struggling_area"
    assert student_recommendations[0]["problem"]["id"] == problem.id
