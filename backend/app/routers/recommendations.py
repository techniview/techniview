from fastapi import APIRouter

from ..core.dependencies import CurrentUser, DbSession
from ..schemas.contracts import RecommendationListResponse
from ..services.recommendations import get_recommendations

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=RecommendationListResponse)
def recommendations(db: DbSession, user: CurrentUser):
    return {"items": get_recommendations(db, user)}
