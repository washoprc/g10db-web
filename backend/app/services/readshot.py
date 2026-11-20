"""readshot バイナリ／テキスト波形パーサ。

TekeTekeKun/readshot.php 相当。次の形式を順に試す:

1. ヘッダ付きバイナリ（nPoints:int32, dtMs:float32, t0Ms:float32 + float32[]）
2. 生 float32 LE 配列（dt は引数または 1.0ms）
3. テキスト（空白／カンマ区切り time,value）
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class ShotTrace:
    """1チャネル分の時系列。"""

    timesMs: np.ndarray
    values: np.ndarray
    source: str


def parseReadshot(
    path: Path,
    *,
    startMs: float = 0.0,
    endMs: float = 200.0,
    defaultDtMs: float = 1.0,
) -> ShotTrace | None:
    """ファイルを読み取り、時間窓で切り出した ShotTrace を返す。"""
    raw = path.read_bytes()
    if not raw:
        return None

    for parser in (_parseHeaderBinary, _parseRawFloat32, _parseText):
        try:
            trace = parser(raw, path, defaultDtMs=defaultDtMs)
        except (ValueError, struct.error, UnicodeDecodeError):
            continue
        if trace is None or len(trace.values) == 0:
            continue
        return _window(trace, startMs, endMs)
    return None


def _window(trace: ShotTrace, startMs: float, endMs: float) -> ShotTrace:
    """時間窓で切り出す。"""
    if endMs <= startMs:
        endMs = startMs + 200.0
    mask = (trace.timesMs >= startMs) & (trace.timesMs <= endMs)
    return ShotTrace(
        timesMs=trace.timesMs[mask],
        values=trace.values[mask],
        source=trace.source,
    )


def _parseHeaderBinary(raw: bytes, path: Path, *, defaultDtMs: float) -> ShotTrace | None:
    """nPoints / dtMs / t0Ms ヘッダ付きバイナリ。"""
    if len(raw) < 12:
        return None
    nPoints, dtMs, t0Ms = struct.unpack_from("<iff", raw, 0)
    if nPoints <= 0 or nPoints > 5_000_000:
        return None
    expected = 12 + nPoints * 4
    if len(raw) < expected:
        return None
    values = np.frombuffer(raw, dtype="<f4", count=nPoints, offset=12).astype(np.float64)
    if not np.isfinite(dtMs) or dtMs <= 0:
        dtMs = defaultDtMs
    times = t0Ms + np.arange(nPoints, dtype=np.float64) * float(dtMs)
    return ShotTrace(timesMs=times, values=values, source=f"header-bin:{path.name}")


def _parseRawFloat32(raw: bytes, path: Path, *, defaultDtMs: float) -> ShotTrace | None:
    """ヘッダ無し float32 LE。"""
    if len(raw) % 4 != 0 or len(raw) < 16:
        return None
    values = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    if values.size < 4:
        return None
    # 極端な値ばかりならバイナリとして不適切とみなす
    if not np.isfinite(values).all():
        return None
    times = np.arange(values.size, dtype=np.float64) * defaultDtMs
    return ShotTrace(timesMs=times, values=values, source=f"raw-f32:{path.name}")


def _parseText(raw: bytes, path: Path, *, defaultDtMs: float) -> ShotTrace | None:
    """テキスト波形。"""
    text = raw.decode("utf-8", errors="ignore")
    times: list[float] = []
    values: list[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) == 1:
            try:
                values.append(float(parts[0]))
                times.append(len(values) * defaultDtMs)
            except ValueError:
                continue
        elif len(parts) >= 2:
            try:
                times.append(float(parts[0]))
                values.append(float(parts[1]))
            except ValueError:
                continue
    if not values:
        return None
    return ShotTrace(
        timesMs=np.asarray(times, dtype=np.float64),
        values=np.asarray(values, dtype=np.float64),
        source=f"text:{path.name}",
    )
