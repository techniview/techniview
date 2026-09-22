from fastapi import APIRouter

from ..core.dependencies import CurrentUser, DbSession
from ..schemas.contracts import CurriculumNodeResponse, ProblemSummaryResponse
from .problems import curriculum_nodes

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


@router.get("", response_model=list[CurriculumNodeResponse])
def get_curriculum(
    db: DbSession,
    user: CurrentUser,
):
    return curriculum_nodes(db, user)


@router.get("/available", response_model=list[ProblemSummaryResponse])
def get_available_curriculum(
    db: DbSession,
    user: CurrentUser,
):
    return [
        node["problem"]
        for node in curriculum_nodes(db, user)
        if node["status"] in {"available", "attempted"}
    ]
