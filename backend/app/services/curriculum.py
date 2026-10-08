"""Technique and problem-type curriculum groupings."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    CurriculumNode,
    Difficulty,
    Problem,
    ProblemState,
    ProblemTag,
    ProblemTagKind,
    StudentPracticeProgress,
    User,
)
from .presentation import problem_summary


def _normalize(value: str) -> str:
    value = re.sub(r"\(.*?\)", "", value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


TECHNIQUE_POOLS: tuple[tuple[str, str, int | None, str, tuple[str, ...], bool], ...] = (
    ("arrays-and-hashing", "Arrays & Hashing", 1, "Foundations", (), False),
    (
        "two-pointers",
        "Two Pointers",
        2,
        "Core Patterns",
        ("arrays-and-hashing",),
        False,
    ),
    ("stack", "Stack", 2, "Core Patterns", ("arrays-and-hashing",), False),
    (
        "binary-search",
        "Binary Search",
        3,
        "Search & Sequences",
        ("arrays-and-hashing",),
        False,
    ),
    (
        "sliding-window",
        "Sliding Window",
        3,
        "Search & Sequences",
        ("two-pointers",),
        False,
    ),
    ("linked-list", "Linked List", 3, "Search & Sequences", ("two-pointers",), False),
    (
        "greedy",
        "Greedy",
        4,
        "Optimization & Structures",
        ("arrays-and-hashing",),
        False,
    ),
    ("intervals", "Intervals", 4, "Optimization & Structures", ("greedy",), False),
    (
        "heap-priority-queue",
        "Heap / Priority Queue",
        4,
        "Optimization & Structures",
        ("arrays-and-hashing",),
        False,
    ),
    ("trees", "Trees", 5, "Recursive Structures", ("linked-list",), False),
    ("tries", "Tries", 5, "Recursive Structures", ("trees",), False),
    (
        "backtracking",
        "Backtracking",
        5,
        "Recursive Structures",
        ("stack", "trees"),
        False,
    ),
    ("graphs", "Graphs", 6, "Graphs & 1-D DP", ("trees",), False),
    (
        "1d-dynamic-programming",
        "1-D Dynamic Programming",
        6,
        "Graphs & 1-D DP",
        ("backtracking",),
        False,
    ),
    ("advanced-graphs", "Advanced Graphs", 7, "Advanced Paths", ("graphs",), False),
    (
        "2d-dynamic-programming",
        "2-D Dynamic Programming",
        7,
        "Advanced Paths",
        ("1d-dynamic-programming",),
        False,
    ),
    (
        "bit-manipulation",
        "Bit Manipulation",
        None,
        "Optional Extensions",
        ("arrays-and-hashing",),
        True,
    ),
    (
        "math-and-geometry",
        "Math & Geometry",
        None,
        "Optional Extensions",
        ("arrays-and-hashing",),
        True,
    ),
)

_TECHNIQUE_ALIASES: dict[str, str] = {
    "array": "arrays-and-hashing",
    "arrays": "arrays-and-hashing",
    "array-and-hashing": "arrays-and-hashing",
    "arrays-hashing": "arrays-and-hashing",
    "arrays-and-hashing": "arrays-and-hashing",
    "two-pointers": "two-pointers",
    "hash-table": "arrays-and-hashing",
    "hash-map": "arrays-and-hashing",
    "hashing": "arrays-and-hashing",
    "prefix-sum": "arrays-and-hashing",
    "string": "arrays-and-hashing",
    "string-matching": "arrays-and-hashing",
    "sorting": "arrays-and-hashing",
    "sort": "arrays-and-hashing",
    "matrix": "arrays-and-hashing",
    "two-pointer": "two-pointers",
    "sliding-window": "sliding-window",
    "stack": "stack",
    "queue": "stack",
    "monotonic-stack": "stack",
    "binary-search": "binary-search",
    "linked-lists": "linked-list",
    "linked-list": "linked-list",
    "tree": "trees",
    "trees": "trees",
    "binary-tree": "trees",
    "binary-search-tree": "trees",
    "trie": "tries",
    "tries": "tries",
    "prefix-tree": "tries",
    "heap": "heap-priority-queue",
    "priority-queue": "heap-priority-queue",
    "heap-priority-queue": "heap-priority-queue",
    "backtracking": "backtracking",
    "recursion": "backtracking",
    "breadth-first-search": "graphs",
    "bfs": "graphs",
    "bfs-dfs": "graphs",
    "depth-first-search": "graphs",
    "dfs": "graphs",
    "graph": "graphs",
    "graphs": "graphs",
    "advanced-graphs": "advanced-graphs",
    "dijkstra": "advanced-graphs",
    "floyd-warshall": "advanced-graphs",
    "topological-sort": "advanced-graphs",
    "union-find": "advanced-graphs",
    "minimum-spanning-tree": "advanced-graphs",
    "dynamic-programming": "1d-dynamic-programming",
    "dynamic-programming-1d": "1d-dynamic-programming",
    "one-dimensional-dynamic-programming": "1d-dynamic-programming",
    "1-d-dynamic-programming": "1d-dynamic-programming",
    "1d-dp": "1d-dynamic-programming",
    "1d-dynamic-programming": "1d-dynamic-programming",
    "dynamic-programming-2d": "2d-dynamic-programming",
    "two-dimensional-dynamic-programming": "2d-dynamic-programming",
    "2-d-dynamic-programming": "2d-dynamic-programming",
    "math-geometry": "math-and-geometry",
    "2d-dp": "2d-dynamic-programming",
    "greedy-algorithm": "greedy",
    "greedy": "greedy",
    "interval": "intervals",
    "intervals": "intervals",
    "bitwise": "bit-manipulation",
    "bit-manipulation": "bit-manipulation",
    "math": "math-and-geometry",
    "geometry": "math-and-geometry",
    "number-theory": "math-and-geometry",
    "modular-exponentiation": "math-and-geometry",
    "sieve-of-eratosthenes": "math-and-geometry",
    "math-and-geometry": "math-and-geometry",
}


def _technique_pool(tag: ProblemTag) -> str:
    normalized = _normalize(tag.name)
    return _TECHNIQUE_ALIASES.get(normalized, "other-techniques")


def _technique_memberships(tags: Iterable[ProblemTag]) -> set[str]:
    return {_technique_pool(tag) for tag in tags}


def _problem_type_memberships(tags: Iterable[ProblemTag]) -> list[ProblemTag]:
    return sorted(
        (tag for tag in tags if tag.kind.value == "problem_type"),
        key=lambda tag: (tag.name.casefold(), tag.slug),
    )


def technique_pool_metadata() -> list[dict]:
    return [
        {
            "slug": slug,
            "name": name,
            "kind": "technique",
            "tier": tier,
            "tier_name": tier_name,
            "optional": optional,
            "prerequisite_pool_slugs": list(prerequisites),
        }
        for slug, name, tier, tier_name, prerequisites, optional in TECHNIQUE_POOLS
    ]


def problem_type_pool_for(tag: ProblemTag) -> dict:
    name = re.sub(r"\s*\(problem type\)\s*$", "", tag.name, flags=re.IGNORECASE)
    return {
        "slug": tag.slug,
        "name": name,
        "kind": "problem_type",
        "tier": None,
        "tier_name": None,
        "optional": False,
        "prerequisite_pool_slugs": [],
    }


def build_curriculum(db: Session, user: User, kind: ProblemTagKind) -> list[dict]:
    nodes = list(
        db.scalars(
            select(CurriculumNode)
            .join(Problem, Problem.id == CurriculumNode.problem_id)
            .options(selectinload(CurriculumNode.problem).selectinload(Problem.tags))
            .where(Problem.owner_id.is_(None), Problem.state == ProblemState.PUBLISHED)
            .order_by(CurriculumNode.priority)
        ).all()
    )
    progress = {
        row.problem_id: row
        for row in db.scalars(
            select(StudentPracticeProgress).where(
                StudentPracticeProgress.student_id == user.id
            )
        )
    }

    pools: dict[str, dict] = {}
    problem_pool_slugs: dict[int, set[str]] = {}
    if kind == ProblemTagKind.TECHNIQUE:
        pools = {pool["slug"]: pool for pool in technique_pool_metadata()}
        for node in nodes:
            memberships = _technique_memberships(
                tag for tag in node.problem.tags if tag.kind == kind
            )
            if not memberships:
                memberships = {"other-techniques"}
            problem_pool_slugs[node.problem_id] = memberships
    else:
        for node in nodes:
            tags = _problem_type_memberships(node.problem.tags)
            memberships = set()
            for tag in tags:
                metadata = problem_type_pool_for(tag)
                pools.setdefault(metadata["slug"], metadata)
                memberships.add(metadata["slug"])
            problem_pool_slugs[node.problem_id] = memberships

    problems_by_pool: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        row = progress.get(node.problem_id)
        if row is not None and row.first_passed_at is not None:
            status = "completed"
        elif row is not None and row.valid_attempt_count > 0:
            status = "attempted"
        else:
            status = "not_started"
        for pool_slug in problem_pool_slugs[node.problem_id]:
            problems_by_pool[pool_slug].append(
                {
                    "problem": node.problem,
                    "priority": node.priority,
                    "status": status,
                    "recommended": False,
                }
            )

    difficulty_order = {
        Difficulty.EASY: 0,
        Difficulty.MEDIUM: 1,
        Difficulty.HARD: 2,
    }
    for items in problems_by_pool.values():
        items.sort(
            key=lambda item: (
                difficulty_order[item["problem"].difficulty],
                item["priority"],
                item["problem"].title.casefold(),
            )
        )

    completed_counts = {
        slug: sum(item["status"] == "completed" for item in items)
        for slug, items in problems_by_pool.items()
    }
    result = []
    ordered_pools = list(pools.values())
    if kind == ProblemTagKind.PROBLEM_TYPE:
        ordered_pools.sort(key=lambda pool: pool["name"].casefold())
    for pool in ordered_pools:
        items = problems_by_pool.get(pool["slug"], [])
        prereqs = pool["prerequisite_pool_slugs"]
        ready = all(completed_counts.get(prereq, 0) > 0 for prereq in prereqs)
        if ready:
            next_item = next(
                (item for item in items if item["status"] != "completed"), None
            )
            if next_item is not None:
                next_item["recommended"] = True
        result.append(
            {
                **pool,
                "problems": [
                    {
                        "problem": problem_summary(item["problem"]),
                        "status": item["status"],
                        "recommended": item["recommended"],
                    }
                    for item in items
                ],
            }
        )
    return result
