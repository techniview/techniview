import json

from app.models import (
    Base,
    CurriculumNode,
    Difficulty,
    ExecutionMode,
    Problem,
    ProblemOrigin,
    ProblemState,
)
from app.seed import seed_demo
from app.services.catalog_import import import_catalog
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def test_new_catalog_archives_previous_catalog_generations(db_session, tmp_path):
    demo_problems = list(
        db_session.scalars(select(Problem).where(Problem.source_dataset == "demo"))
    )
    demo_ids = {problem.id for problem in demo_problems}
    assert len(demo_ids) == 2

    new_dataset = "APPS and APPS+ (TechniView Trail audited 2026-10-07 v2)"
    old_problem = Problem(
        origin=ProblemOrigin.IMPORTED,
        state=ProblemState.PUBLISHED,
        title="Old catalog problem",
        prompt="Archived when the reviewed catalog is imported.",
        difficulty=Difficulty.EASY,
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
        starter_code="def solve(value): pass",
        canonical_solution="def solve(value): return value",
        source_dataset="APPS and APPS+ (combined, deduplicated)",
        source_problem_id="old-problem",
    )
    db_session.add(old_problem)
    db_session.flush()
    old_id = old_problem.id
    db_session.add(CurriculumNode(problem_id=old_id, priority=101))

    old_reviewed_problem = Problem(
        origin=ProblemOrigin.IMPORTED,
        state=ProblemState.PUBLISHED,
        title="Old reviewed catalog problem",
        prompt="Archived when a replacement catalog is imported.",
        difficulty=Difficulty.EASY,
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
        starter_code="def solve(value): pass",
        canonical_solution="def solve(value): return value",
        source_dataset="APPS and APPS+ (reviewed catalog 2026-10-07)",
        source_problem_id="old-reviewed-problem",
    )
    db_session.add(old_reviewed_problem)
    db_session.flush()
    old_reviewed_id = old_reviewed_problem.id
    db_session.add(CurriculumNode(problem_id=old_reviewed_id, priority=102))
    db_session.commit()

    catalog = {
        "schema_version": 1,
        "source_dataset": new_dataset,
        "source_version": "a" * 64,
        "problem_count": 1,
        "curriculum_count": 1,
        "curriculum_problem_ids": ["new-problem"],
        "attribution": "APPS and APPS+",
        "license": "MIT",
        "problems": [
            {
                "source_problem_id": "new-problem",
                "title": "New catalog problem",
                "prompt": "Return the supplied value.",
                "difficulty": "easy",
                "source_category": "APPS+:interview",
                "execution_mode": "call_based",
                "function_name": "solve",
                "starter_code": "def solve(value): pass",
                "canonical_solution": "def solve(value): return value",
                "test_cases": [
                    {
                        "visibility": "public",
                        "input": "[1]",
                        "expected_output": "1",
                    }
                ],
                "tags": [
                    {
                        "kind": "technique",
                        "name": "Arrays & Hashing",
                        "slug": "arrays-and-hashing",
                    },
                    {
                        "kind": "problem_type",
                        "name": "Array / String (Problem Type)",
                        "slug": "array-string-problem-type",
                    },
                ],
                "validation": {"test_cases_verified": True},
            }
        ],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    result = import_catalog(db_session, catalog_path)

    assert result == {
        "imported": 1,
        "already_present": 0,
        "catalog_total": 1,
        "curriculum_total": 1,
    }
    assert db_session.get(Problem, old_id).state == ProblemState.ARCHIVED
    assert db_session.get(CurriculumNode, old_id) is None
    assert db_session.get(Problem, old_reviewed_id).state == ProblemState.ARCHIVED
    assert db_session.get(CurriculumNode, old_reviewed_id) is None
    assert all(
        db_session.get(Problem, problem_id).state == ProblemState.ARCHIVED
        for problem_id in demo_ids
    )
    assert all(
        db_session.get(CurriculumNode, problem_id) is None for problem_id in demo_ids
    )
    new_problem = db_session.scalar(
        select(Problem).where(
            Problem.source_dataset == catalog["source_dataset"],
            Problem.source_problem_id == "new-problem",
        )
    )
    assert new_problem is not None
    assert db_session.get(CurriculumNode, new_problem.id).priority == 101

    repeated_result = import_catalog(db_session, catalog_path)
    assert repeated_result == {
        "imported": 0,
        "already_present": 1,
        "catalog_total": 1,
        "curriculum_total": 1,
    }
    assert new_problem.state == ProblemState.PUBLISHED


def test_demo_seed_does_not_add_published_problems_after_catalog_load():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Problem(
                origin=ProblemOrigin.IMPORTED,
                state=ProblemState.PUBLISHED,
                title="Catalog problem",
                prompt="Catalog fixture.",
                difficulty=Difficulty.EASY,
                execution_mode=ExecutionMode.CALL_BASED,
                function_name="solve",
                starter_code="def solve(value): pass",
                canonical_solution="def solve(value): return value",
                source_dataset="test catalog",
                source_problem_id="catalog-problem",
            )
        )
        db.commit()

        seed_demo(db)

        published_count = db.scalar(
            select(func.count())
            .select_from(Problem)
            .where(Problem.owner_id.is_(None), Problem.state == ProblemState.PUBLISHED)
        )
        demo_problems = list(
            db.scalars(select(Problem).where(Problem.source_dataset == "demo"))
        )
        assert published_count == 1
        assert len(demo_problems) == 2
        assert all(problem.state == ProblemState.ARCHIVED for problem in demo_problems)
        assert not db.scalars(
            select(CurriculumNode).where(
                CurriculumNode.problem_id.in_([problem.id for problem in demo_problems])
            )
        ).all()
