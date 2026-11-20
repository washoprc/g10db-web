"""波形取得サービス（Ha / DM / NL / VCC）。

PHP TekeTekeKun + jpgraph 相当。本番では DATA_ROOT 上のバイナリ／テキストを読み、
無い場合は物理的に妥当なデモ波形を返す。
"""

from __future__ import annotations

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
from app.services.configLoader import loadGroupList, loadTableList


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
    # フォールバック
    fallback = {
        "Ha": ["Ha_CC", "Ha_E", "Ha_W"],
        "DM": ["DM_CC", "DM_A"],
        "NL": ["NL_CC", "NL_A"],
        "VCC": ["VCC1", "VCC2"],
    }
    return fallback[kind]


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
            values = 0.5 + 0.4 * np.sin(0.05 * times + phase)
        else:
            values = 0.2 * np.sin(0.12 * times + phase) + 0.05 * np.sin(0.4 * times)
        points = [
            WaveformPoint(t=float(t), v=float(v))
            for t, v in zip(times, values, strict=True)
        ]
        series.append(WaveformSeries(name=name, unit=meta["unit"], points=points))
    return series


def loadFileSeries(
    shotNo: int,
    kind: WaveformKind,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries] | None:
    """DATA_ROOT/{shotNo}/{kind}*.csv|txt があれば読み込む。

    期待フォーマット: 空白またはカンマ区切りの time,value
    """
    root = getSettings().dataRoot
    shotDir = root / str(shotNo)
    if not shotDir.is_dir():
        return None

    names = channelNamesFor(kind)
    meta = resolveKindMeta(kind)
    series: list[WaveformSeries] = []
    found = False
    for name in names:
        candidates = list(shotDir.glob(f"{kind}_{name}.*")) + list(
            shotDir.glob(f"{name}.*")
        )
        if not candidates:
            continue
        points = readTraceFile(candidates[0], startMs, endMs)
        if points:
            found = True
            series.append(WaveformSeries(name=name, unit=meta["unit"], points=points))
    return series if found else None


def readTraceFile(path: Path, startMs: float, endMs: float) -> list[WaveformPoint]:
    """テキスト波形ファイルを読む。"""
    points: list[WaveformPoint] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0])
            v = float(parts[1])
        except ValueError:
            continue
        if t < startMs or t > endMs:
            continue
        points.append(WaveformPoint(t=t, v=v))
    return points


def getWaveform(
    shotNo: int,
    kind: WaveformKind,
    startMs: float = 0.0,
    endMs: float = 200.0,
) -> WaveformResponse:
    """指定ショット・診断の波形を返す。"""
    settings = getSettings()
    fileSeries = None if settings.useDemo else loadFileSeries(shotNo, kind, startMs, endMs)
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
        note = "データファイルが見つからないためデモ波形を返しています"
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
        "rmsHint": round(math.sqrt(0.5), 3),
    }
