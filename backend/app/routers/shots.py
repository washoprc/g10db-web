"""ショット検索 API。

- GET /api/shots/latest  … 最新（last.php）
- GET /api/shots/by-number … 番号指定（sn.php）
- GET /api/shots/by-date   … 日付指定
任意 SQL エンドポイントは意図的に提供しない。
"""

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ShotListResponse
from app.services import shotService

router = APIRouter(prefix="/shots", tags=["shots"])


@router.get("/latest", response_model=ShotListResponse)
def getLatestShots(
    limit: int = Query(default=10, ge=1, le=30, description="取得件数"),
) -> ShotListResponse:
    """最新ショットを取得する。"""
    return shotService.queryLatest(limit)


@router.get("/by-number", response_model=ShotListResponse)
def getShotsByNumber(
    start: int = Query(..., ge=1, description="開始ショット番号"),
    limit: int = Query(default=10, ge=1, le=30, description="取得件数"),
) -> ShotListResponse:
    """指定ショット番号以降を取得する。"""
    return shotService.queryByNumber(start, limit)


@router.get("/by-date", response_model=ShotListResponse)
def getShotsByDate(
    date: str = Query(..., description="YYYY-MM-DD または YYYYMMDD"),
    limit: int = Query(default=10, ge=1, le=30, description="取得件数"),
) -> ShotListResponse:
    """指定日付のショットを取得する。"""
    try:
        onDate = shotService.parseDateParam(date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return shotService.queryByDate(onDate, limit)
