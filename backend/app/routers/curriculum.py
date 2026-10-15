from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select

from ..core.dependencies import CurrentUser, DbSession
from ..models import CurriculumEdge, ProblemTagKind
from ..schemas.contracts import CurriculumPoolResponse, ProblemSummaryResponse
from ..services.curriculum import build_curriculum

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


@router.get("/graph")
def get_curriculum_graph(db: DbSession, user: CurrentUser):
    pools = build_curriculum(db, user, ProblemTagKind.TECHNIQUE)
    nodes = {}
    for pool in pools:
        for item in pool["problems"]:
            nodes[item["problem"]["id"]] = item
    edges = [
        {
            "prerequisite_problem_id": edge.prerequisite_problem_id,
            "problem_id": edge.problem_id,
        }
        for edge in db.scalars(select(CurriculumEdge))
        if edge.problem_id in nodes and edge.prerequisite_problem_id in nodes
    ]
    return {"nodes": list(nodes.values()), "edges": edges}


@router.get("", response_model=list[CurriculumPoolResponse])
def get_curriculum(
    db: DbSession,
    user: CurrentUser,
    kind: Literal["technique", "problem_type"] = "technique",
):
    return build_curriculum(db, user, ProblemTagKind(kind))


@router.get("/available", response_model=list[ProblemSummaryResponse])
def get_available_curriculum(
    db: DbSession,
    user: CurrentUser,
):
    pools = build_curriculum(db, user, ProblemTagKind.TECHNIQUE)
    problems: dict[int, dict] = {}
    for pool in pools:
        for item in pool["problems"]:
            if item["recommended"] or item["status"] == "attempted":
                problems[item["problem"]["id"]] = item["problem"]
    return list(problems.values())
