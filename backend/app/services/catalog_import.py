"""Import a validated external problem catalog into the application database."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CurriculumNode,
    Difficulty,
    ExecutionMode,
    Problem,
    ProblemOrigin,
    ProblemState,
    ProblemTag,
    ProblemTagKind,
    ProblemTestCase,
    TestVisibility,
)

_LEGACY_CATALOG_DATASETS = (
    "demo",
    "APPS+ (StepCoder APPS_PLUS_FINAL)",
    "APPS and APPS+ (combined, deduplicated)",
    "APPS and APPS+ (reviewed catalog 2026-10-07)",
    "APPS and APPS+ (reviewed catalog with checker-safe replacements 2026-10-07)",
    "APPS and APPS+ (TechniView Trail audited 2026-10-07)",
    "APPS and APPS+ (TechniView Trail audited 2026-10-07 v2)",
)


def _load_catalog(path: Path) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("Unsupported catalog schema version.")
    problems = catalog.get("problems", [])
    if not problems:
        raise ValueError("The catalog must contain at least one problem.")
    if catalog.get("problem_count") != len(problems):
        raise ValueError("Catalog problem_count does not match its problem rows.")
    curriculum_ids = catalog.get("curriculum_problem_ids")
    if not isinstance(curriculum_ids, list) or not curriculum_ids:
        raise ValueError("Catalog must define its curriculum_problem_ids.")
    if catalog.get("curriculum_count") != len(curriculum_ids):
        raise ValueError("Catalog curriculum_count does not match its membership list.")
    source_ids = {problem.get("source_problem_id") for problem in problems}
    if (
        len(set(curriculum_ids)) != len(curriculum_ids)
        or not set(curriculum_ids) <= source_ids
    ):
        raise ValueError("Curriculum IDs must be unique catalog problem IDs.")
    return catalog


def _validate_problem(problem: Mapping, source_version: str) -> None:
    required = (
        "source_problem_id",
        "title",
        "prompt",
        "difficulty",
        "source_category",
        "execution_mode",
        "function_name",
        "starter_code",
        "canonical_solution",
        "test_cases",
        "tags",
    )
    if any(not problem.get(field) for field in required):
        raise ValueError("Catalog problem is missing a required field.")
    if problem["difficulty"] not in {item.value for item in Difficulty}:
        raise ValueError(f"Invalid difficulty for {problem['source_problem_id']}.")
    if problem["execution_mode"] not in {item.value for item in ExecutionMode}:
        raise ValueError(f"Invalid execution mode for {problem['source_problem_id']}.")
    validation = problem.get("validation", {})
    if not (
        validation.get("source_tests_verified") or validation.get("test_cases_verified")
    ):
        raise ValueError(
            f"Problem test cases are not verified for {problem['source_problem_id']}."
        )
    if validation.get("supplemental_cases_rejected"):
        raise ValueError(
            f"A supplemental case failed for {problem['source_problem_id']}."
        )
    if problem.get("unsupported_imports"):
        raise ValueError(
            f"Unsupported imports for {problem['source_problem_id']}: "
            f"{problem['unsupported_imports']}"
        )
    cases = problem["test_cases"]
    if not cases or cases[0].get("visibility") != TestVisibility.PUBLIC.value:
        raise ValueError(
            f"The first test case must be public for {problem['source_problem_id']}."
        )
    if any(case.get("visibility") != TestVisibility.HIDDEN.value for case in cases[1:]):
        raise ValueError(
            f"Only the first case may be public for {problem['source_problem_id']}."
        )
    kinds = {tag.get("kind") for tag in problem["tags"]}
    if not {ProblemTagKind.TECHNIQUE.value, ProblemTagKind.PROBLEM_TYPE.value} <= kinds:
        raise ValueError(
            f"Both typed tag groups are required for {problem['source_problem_id']}."
        )
    if problem.get("source_version") not in {None, source_version}:
        raise ValueError(
            "Problem source version does not match catalog source version."
        )


def _tag_for(db: Session, value: Mapping) -> ProblemTag:
    kind = ProblemTagKind(value["kind"])
    slug = value["slug"]
    tag = db.scalar(select(ProblemTag).where(ProblemTag.slug == slug))
    if tag is not None:
        if tag.kind != kind or tag.name != value["name"]:
            raise ValueError(f"Catalog tag conflicts with existing slug {slug!r}.")
        return tag
    tag = db.scalar(select(ProblemTag).where(ProblemTag.name == value["name"]))
    if tag is not None:
        if tag.kind != kind:
            raise ValueError(
                f"Catalog tag conflicts with existing name {value['name']!r}."
            )
        return tag
    tag = ProblemTag(name=value["name"], slug=slug, kind=kind)
    db.add(tag)
    db.flush()
    return tag


def import_catalog(db: Session, path: Path) -> dict[str, int]:
    catalog = _load_catalog(path)
    problems: list[dict] = catalog["problems"]
    source_version = catalog["source_version"]
    if not re.fullmatch(r"[0-9a-f]{64}", source_version):
        raise ValueError("Catalog source_version must be a SHA-256 checksum.")
    source_ids = [problem.get("source_problem_id") for problem in problems]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Catalog source problem IDs must be unique.")
    for problem in problems:
        _validate_problem(problem, source_version)

    legacy_problems = list(
        db.scalars(
            select(Problem)
            .where(Problem.source_dataset.in_(_LEGACY_CATALOG_DATASETS))
            .where(Problem.source_dataset != catalog["source_dataset"])
        )
    )
    for problem in legacy_problems:
        node = db.get(CurriculumNode, problem.id)
        if node is not None:
            db.delete(node)
        problem.state = ProblemState.ARCHIVED
    db.flush()

    curriculum_priority = {
        source_id: priority
        for priority, source_id in enumerate(
            catalog["curriculum_problem_ids"], start=101
        )
    }
    imported = 0
    existing_count = 0
    catalog_problems: list[Problem] = []
    for item in problems:
        source_id = item["source_problem_id"]
        existing = db.scalar(
            select(Problem).where(
                Problem.source_dataset == catalog["source_dataset"],
                Problem.source_problem_id == source_id,
            )
        )
        if existing is not None:
            if existing.source_version != source_version:
                raise ValueError(
                    f"{source_id} is already imported from a different source version."
                )
            problem = existing
            existing_count += 1
            problem.difficulty = Difficulty(item["difficulty"])
            problem.source_category = item["source_category"]
            problem.attribution = catalog["attribution"]
            problem.license = catalog["license"]
            problem.tags = [_tag_for(db, tag) for tag in item["tags"]]
        else:
            tags = [_tag_for(db, tag) for tag in item["tags"]]
            problem = Problem(
                origin=ProblemOrigin.IMPORTED,
                state=ProblemState.PUBLISHED,
                title=item["title"],
                prompt=item["prompt"],
                difficulty=Difficulty(item["difficulty"]),
                execution_mode=ExecutionMode(item["execution_mode"]),
                function_name=item["function_name"],
                starter_code=item["starter_code"],
                canonical_solution=item["canonical_solution"],
                source_dataset=catalog["source_dataset"],
                source_problem_id=source_id,
                source_version=source_version,
                source_category=item["source_category"],
                attribution=catalog["attribution"],
                license=catalog["license"],
                tags=tags,
                test_cases=[
                    ProblemTestCase(
                        case_order=case_order,
                        visibility=TestVisibility(test_case["visibility"]),
                        input=test_case["input"],
                        expected_output=test_case["expected_output"],
                    )
                    for case_order, test_case in enumerate(item["test_cases"], start=1)
                ],
            )
            db.add(problem)
            db.flush()
            imported += 1
        catalog_problems.append(problem)

    source_problems = list(
        db.scalars(
            select(Problem).where(Problem.source_dataset == catalog["source_dataset"])
        )
    )
    for problem in source_problems:
        node = db.get(CurriculumNode, problem.id)
        if node is not None:
            node.priority = -problem.id
    db.flush()

    for problem in source_problems:
        priority = curriculum_priority.get(problem.source_problem_id)
        node = db.get(CurriculumNode, problem.id)
        if priority is None:
            if node is not None:
                db.delete(node)
        elif node is None:
            db.add(CurriculumNode(problem_id=problem.id, priority=priority))
        else:
            node.priority = priority

    db.commit()
    return {
        "imported": imported,
        "already_present": existing_count,
        "catalog_total": len(catalog_problems),
        "curriculum_total": len(curriculum_priority),
    }
