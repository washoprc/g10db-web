"""波形取得サービス（Ha / DM / NL / VCC）。

処理順:
1. DATA_ROOT 上のローカルファイル
2. FTP 取得（設定時）→ readshot パース → 診断後処理
3. デモ合成波形（USE_DEMO=1 またはフォールバック）

任意 SQL は使わない。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np

from app.config import getSettings
from app.models.schemas import (
    WaveformKind,
    WaveformPoint,
    WaveformResponse,
    WaveformSeries,
)
from app.services import ftpClient
from app.services.configLoader import loadGroupList, loadTableList
from app.services.processors import processTrace
from app.services.readshot import parseReadshot

logger = logging.getLogger(__name__)


def resolveKindMeta(kind: WaveformKind) -> dict[str, str]:
    """診断種別の表示メタ情報。"""
    defaults = {
        "Ha": {"label": "Hα", "unit": "a.u."},
        "DM": {"label": "Diamagnetism", "unit": "Wb"},
        "NL": {"label": "Line density", "unit": "m^-2"},
        "VCC": {"label": "VCC", "unit": "V"},
    }
    groups = loadGroupList().get("groups", [])
    for group in groups:
        if group.get("id") == kind:
            return {
                "label": group.get("label", defaults[kind]["label"]),
                "unit": group.get("unit", defaults[kind]["unit"]),
            }
    return defaults[kind]


def channelNamesFor(kind: WaveformKind) -> list[str]:
    """TableList からチャネル名を取得する。"""
    tables = loadTableList().get("tables", [])
    for table in tables:
        if table.get("id") == kind:
            channels = table.get("channels", [])
            if channels:
                return [str(c) for c in channels]
    fallback = {
        "Ha": ["Ha_CC", "Ha_E", "Ha_W", "Ha_Barrier", "Ha_Anchor"],
        "DM": ["DM_CC", "DM_A", "DM_Barrier", "DM_Plug"],
        "NL": ["NL_CC", "NL_A", "NLEA", "NLEB", "NL_Barrier"],
        "VCC": ["VCC1", "VCC2", "VCC3", "VCC4"],
    }
    return fallback[kind]


def ftpDirFor(kind: WaveformKind) -> str:
    """FTP 上の診断ディレクトリ名。"""
    groups = loadGroupList().get("groups", [])
    for group in groups:
        if group.get("id") == kind and group.get("ftpDir"):
            return str(group["ftpDir"])
    return kind


def demoSeries(kind: WaveformKind, startMs: float, endMs: float) -> list[WaveformSeries]:
    """デモ用の合成波形を生成する。"""
    meta = resolveKindMeta(kind)
    names = channelNamesFor(kind)
    if endMs <= startMs:
        endMs = startMs + 200.0
    times = np.linspace(startMs, endMs, 400)
    series: list[WaveformSeries] = []
    for index, name in enumerate(names):
        phase = index * 0.7
        if kind == "Ha":
            values = np.exp(-((times - (startMs + 40)) / 25) ** 2) * (1.0 + 0.2 * index)
        elif kind == "DM":
            values = np.clip((times - startMs) / 80.0, 0, 1) * (0.8 + 0.1 * index)
            values = values * np.exp(-(times - startMs) / 180.0)
        elif kind == "NL":
            values = (0.5 + 0.4 * np.sin(0.05 * times + phase)) * 1.0e18
        else:
            values = 0.2 * np.sin(0.12 * times + phase) + 0.05 * np.sin(0.4 * times)
        points = [
            WaveformPoint(t=float(t), v=float(v))
            for t, v in zip(times, values, strict=True)
        ]
        series.append(WaveformSeries(name=name, unit=meta["unit"], points=points))
    return series


def findLocalChannelFiles(shotNo: int, kind: WaveformKind, channel: str) -> list[Path]:
    """DATA_ROOT 配下の候補パスを列挙する。"""
    root = getSettings().dataRoot
    shotDir = root / str(shotNo)
    candidates = [
        shotDir / kind / f"{channel}.dat",
        shotDir / kind / f"{channel}.txt",
        shotDir / kind / f"{channel}.csv",
        shotDir / f"{kind}_{channel}.dat",
        shotDir / f"{channel}.dat",
        root / "ftp_cache" / str(shotNo) / kind / f"{channel}.dat",
    ]
    return [p for p in candidates if p.is_file() and p.stat().st_size > 0]


def loadProcessedSeries(
    shotNo: int,
    kind: WaveformKind,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries] | None:
    """ローカル／FTP からチャネルを読み、後処理して返す。"""
    meta = resolveKindMeta(kind)
    names = channelNamesFor(kind)
    series: list[WaveformSeries] = []

    # 必要なら FTP で不足分を埋める
    missing = [name for name in names if not findLocalChannelFiles(shotNo, kind, name)]
    if missing and ftpClient.isFtpConfigured() and not getSettings().useDemo:
        ftpClient.fetchShotFiles(shotNo, ftpDirFor(kind), missing)

    for name in names:
        files = findLocalChannelFiles(shotNo, kind, name)
        if not files:
            continue
        trace = parseReadshot(files[0], startMs=startMs, endMs=endMs)
        if trace is None or len(trace.values) == 0:
            continue
        processed = processTrace(kind, name, trace, shotNo=shotNo)
        points = [
            WaveformPoint(t=float(t), v=float(v))
            for t, v in zip(processed.timesMs, processed.values, strict=True)
            if math.isfinite(float(t)) and math.isfinite(float(v))
        ]
        if points:
            series.append(WaveformSeries(name=name, unit=meta["unit"], points=points))

    return series if series else None


def getWaveform(
    shotNo: int,
    kind: WaveformKind,
    startMs: float = 0.0,
    endMs: float = 200.0,
) -> WaveformResponse:
    """指定ショット・診断の波形を返す。"""
    settings = getSettings()
    fileSeries = None
    if not settings.useDemo:
        try:
            fileSeries = loadProcessedSeries(shotNo, kind, startMs, endMs)
        except Exception as exc:  # noqa: BLE001 — API ではフォールバックを優先
            logger.warning("waveform load failed: %s", exc)
            fileSeries = None

    if fileSeries:
        return WaveformResponse(
            shotNo=shotNo,
            kind=kind,
            startMs=startMs,
            endMs=endMs,
            series=fileSeries,
            demoMode=False,
        )

    note = None
    if not settings.useDemo:
        note = "データファイル／FTP 取得に失敗したためデモ波形を返しています"
    return WaveformResponse(
        shotNo=shotNo,
        kind=kind,
        startMs=startMs,
        endMs=endMs,
        series=demoSeries(kind, startMs, endMs),
        demoMode=True,
        note=note,
    )


def summarizeKind(kind: WaveformKind) -> dict[str, object]:
    """診断種別の設定サマリ（デバッグ／UI 用）。"""
    meta = resolveKindMeta(kind)
    return {
        "kind": kind,
        "label": meta["label"],
        "unit": meta["unit"],
        "channels": channelNamesFor(kind),
        "ftpDir": ftpDirFor(kind),
    }
