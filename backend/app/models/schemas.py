"""API 入出力スキーマ。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """ヘルスチェック応答。"""

    status: str
    demoMode: bool
    database: str


class ShotSearchQuery(BaseModel):
    """ショット検索の共通上限。"""

    limit: int = Field(default=10, ge=1, le=30, description="取得件数（最大30）")


class ShotRow(BaseModel):
    """mainview の1行（列名は DB のまま保持）。"""

    shotNo: int | None = None
    columns: dict[str, Any] = Field(default_factory=dict)


class PanelCell(BaseModel):
    """ShowTable セル内の 1 行。"""

    text: str
    isShotLink: bool = False
    shotNo: int | None = None


class PanelGroup(BaseModel):
    """1 グループ列分の縦積みセル。"""

    cells: list[PanelCell] = Field(default_factory=list)


class ShotListResponse(BaseModel):
    """ショット一覧応答。"""

    mode: Literal["latest", "byNumber", "byDate"]
    count: int
    items: list[ShotRow]
    groupNames: list[str] = Field(default_factory=list)
    panels: list[list[PanelGroup]] = Field(default_factory=list)
    demoMode: bool = False
    matchedDate: str | None = None
    closestFallback: bool = False


WaveformKind = Literal["Ha", "DM", "NL", "VCC"]


class WaveformPoint(BaseModel):
    """波形の1サンプル。"""

    t: float
    v: float


class WaveformSeries(BaseModel):
    """1チャネル分の波形。"""

    name: str
    unit: str = ""
    points: list[WaveformPoint]


class WaveformResponse(BaseModel):
    """波形 API 応答。"""

    shotNo: int
    kind: WaveformKind
    startMs: float
    endMs: float
    series: list[WaveformSeries]
    demoMode: bool = False
    note: str | None = None
