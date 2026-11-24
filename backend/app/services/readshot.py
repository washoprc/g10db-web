"""readshot バイナリ／テキスト波形パーサ。

TekeTekeKun/readshot.php 相当。次の形式を順に試す:

1. レガシー CAMAC（拡張子なし / .dat 優先 — kasumi ポートファイル）
2. ヘッダ付きバイナリ（nPoints:int32, dtMs:float32, t0Ms:float32 + float32[]）
3. 生 float32 LE 配列（dt は引数または 1.0ms）
4. テキスト（空白／カンマ区切り time,value）
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# CAMAC ヘッダ: 80 × uint16 big-endian = 160 bytes
CAMAC_HEADER_BYTES = 160


@dataclass
class ShotTrace:
    """1チャネル分の時系列。"""

    timesMs: np.ndarray
    values: np.ndarray
    source: str


def loadCamacSamples(path: Path, *, defaultDtMs: float = 1.0) -> ShotTrace | None:
    """ポートファイルを末尾まで読み、先頭 160 バイトを除いたサンプル列を返す。

    計算用の読み込み。表示時間窓では切らない。
    ヘッダは 80 × uint16（160 バイト）。残りは big-endian uint16。
    端数 1 バイトは不完全なサンプルとして捨てる。

    Args:
        path: ポートファイルのパス。
        defaultDtMs: サンプル間隔 [ms]。0 以下のときは 1.0。

    Returns:
        全サンプルの ShotTrace。空、またはヘッダしか無いときは None。
    """
    raw = path.read_bytes()
    if len(raw) <= CAMAC_HEADER_BYTES:
        return None
    payload = raw[CAMAC_HEADER_BYTES:]
    if len(payload) % 2 == 1:
        payload = payload[:-1]
    if len(payload) < 4:
        return None
    values = np.frombuffer(payload, dtype=">u2").astype(np.float64)
    if values.size < 2:
        return None
    dtMs = defaultDtMs if defaultDtMs > 0 else 1.0
    times = np.arange(values.size, dtype=np.float64) * float(dtMs)
    return ShotTrace(
        timesMs=times,
        values=values,
        source=f"legacy-camac:{path.name}",
    )


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

    # kasumi ポートは拡張子なし / .dat — 誤って header-bin に食われないよう CAMAC 優先
    suffix = path.suffix.lower()
    if suffix in ("", ".dat"):
        parsers = (_parseLegacyCamac, _parseHeaderBinary, _parseRawFloat32, _parseText)
    else:
        parsers = (_parseHeaderBinary, _parseLegacyCamac, _parseRawFloat32, _parseText)

    for parser in parsers:
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
    """nPoints / dtMs / t0Ms ヘッダ付きバイナリ（厳密検証）。"""
    if len(raw) < 12:
        return None
    nPoints, dtMs, t0Ms = struct.unpack_from("<iff", raw, 0)
    # 誤検出抑制: 点数・サンプリング・時刻・長さ・有限値を厳密に要求
    if nPoints < 8 or nPoints > 5_000_000:
        return None
    if not np.isfinite(dtMs) or not (0.0 < float(dtMs) <= 1000.0):
        return None
    if not np.isfinite(t0Ms) or abs(float(t0Ms)) >= 1e6:
        return None
    expected = 12 + nPoints * 4
    if len(raw) < expected:
        return None
    surplus = len(raw) - expected
    if surplus > 64:
        return None
    values = np.frombuffer(raw, dtype="<f4", count=nPoints, offset=12).astype(np.float64)
    if not np.isfinite(values).all():
        return None
    times = float(t0Ms) + np.arange(nPoints, dtype=np.float64) * float(dtMs)
    return ShotTrace(timesMs=times, values=values, source=f"header-bin:{path.name}")


def _parseLegacyCamac(raw: bytes, path: Path, *, defaultDtMs: float) -> ShotTrace | None:
    """レガシー CAMAC バイナリ（PHP readshot.php 互換）。

    先頭 160 バイト（80 × uint16 BE）をスキップし、
    残りを big-endian uint16（偶数長）または uint8 サンプルとして読む。
    """
    if len(raw) <= CAMAC_HEADER_BYTES:
        return None
    # ヘッダが「小さな整数の並び」っぽいかざっくり確認（誤検出抑制）
    header = np.frombuffer(raw, dtype=">u2", count=80)
    if header.size != 80:
        return None

    payload = raw[CAMAC_HEADER_BYTES:]
    if not payload:
        return None

    values: np.ndarray | None = None
    if len(payload) % 2 == 0 and len(payload) >= 4:
        asU16 = np.frombuffer(payload, dtype=">u2").astype(np.float64)
        # 全ゼロや極端に短い列は棄却
        if asU16.size >= 4:
            values = asU16
    if values is None:
        asU8 = np.frombuffer(payload, dtype="u1").astype(np.float64)
        if asU8.size < 4:
            return None
        values = asU8

    dtMs = defaultDtMs if defaultDtMs > 0 else 1.0
    times = np.arange(values.size, dtype=np.float64) * float(dtMs)
    return ShotTrace(
        timesMs=times,
        values=values,
        source=f"legacy-camac:{path.name}",
    )


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
