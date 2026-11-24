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


@router.get("/meta/status")
def getWaveformStatus() -> dict:
    """波形ランタイム状態（USE_DEMO / FTP 設定・probe）。"""
    return waveformService.waveformRuntimeStatus()


@router.get("/{shotNo}/diagnose")
def diagnoseWaveform(
    shotNo: int,
    kind: KindParam = Query(default="Ha", description="診断種別"),
    startMs: float | None = Query(
        default=None,
        description="開始時刻 [ms]。省略時は 50（TekeTekeKun 相当）",
    ),
    endMs: float | None = Query(
        default=None,
        description="終了時刻 [ms]。省略時は long=450 / short=250",
    ),
) -> dict:
    """ショット波形の取得・パース診断。"""
    return waveformService.diagnoseWaveform(shotNo, kind, startMs, endMs)


@router.get("/{shotNo}/{kind}", response_model=WaveformResponse)
def getWaveform(
    shotNo: int,
    kind: KindParam,
    startMs: float | None = Query(
        default=None,
        description="開始時刻 [ms]。省略時は 50（TekeTekeKun 相当）",
    ),
    endMs: float | None = Query(
        default=None,
        description="終了時刻 [ms]。省略時は long=450 / short=250",
    ),
) -> WaveformResponse:
    """指定ショットの診断波形を返す。"""
    return waveformService.getWaveform(shotNo, kind, startMs, endMs)
