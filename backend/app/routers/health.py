"""ヘルスチェック。"""

from fastapi import APIRouter

from app.config import getSettings
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def getHealth() -> HealthResponse:
    """API の稼働状態を返す。"""
    settings = getSettings()
    return HealthResponse(
        status="ok",
        demoMode=settings.useDemo,
        database=settings.dbName,
    )
