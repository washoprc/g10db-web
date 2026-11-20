"""波形 API（Ha / DM / NL / VCC）。"""

from typing import Literal

from fastapi import APIRouter, Query

from app.models.schemas import WaveformResponse
from app.services import configLoader, waveformService

router = APIRouter(prefix="/waveforms", tags=["waveforms"])

KindParam = Literal["Ha", "DM", "NL", "VCC"]


@router.get("/meta/config")
def getWaveformConfig() -> dict:
    """GroupList / TableList / 校正ファイルのサマリ。"""
    return configLoader.describeConfig()


@router.get("/{shotNo}/{kind}", response_model=WaveformResponse)
def getWaveform(
    shotNo: int,
    kind: KindParam,
    startMs: float = Query(default=0.0, description="開始時刻 [ms]"),
    endMs: float = Query(default=200.0, description="終了時刻 [ms]"),
) -> WaveformResponse:
    """指定ショットの診断波形を返す。"""
    return waveformService.getWaveform(shotNo, kind, startMs, endMs)
