from typing import Literal

from fastapi import APIRouter

from ..core.dependencies import CurrentUser, DbSession
from ..models import ProblemTagKind
from ..schemas.contracts import CurriculumPoolResponse, ProblemSummaryResponse
from ..services.curriculum import build_curriculum

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


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
