"""診断種別ごとの波形後処理。

TekeTekeKun の HaGraph / DMGraph / NLupGraph2 / VCCGraph 相当。
校正ファイルは config/Ha_coef と config/NL から読む。
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from app.services.configLoader import configRoot
from app.services.readshot import ShotTrace


def loadCoefMap(relativePath: str) -> dict[str, tuple[float, float]]:
    """`channel scale offset` 形式の校正ファイルを読む。"""
    path = configRoot() / relativePath
    result: dict[str, tuple[float, float]] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"[\s,]+", line)
        if len(parts) < 2:
            continue
        channel = parts[0]
        try:
            scale = float(parts[1])
            offset = float(parts[2]) if len(parts) > 2 else 0.0
        except ValueError:
            continue
        result[channel] = (scale, offset)
    return result


def applyHa(trace: ShotTrace, channel: str) -> ShotTrace:
    """Ha: scale * raw + offset（Ha_coef）。"""
    coefs = loadCoefMap("Ha_coef/ha_coef.txt")
    # 個別ファイル名（旧 Ha_coef/<channel>.txt）も探索
    channelFile = configRoot() / "Ha_coef" / f"{channel}.txt"
    if channelFile.is_file():
        extra = loadCoefMap(f"Ha_coef/{channel}.txt")
        coefs.update(extra)
    scale, offset = coefs.get(channel, (1.0, 0.0))
    return ShotTrace(
        timesMs=trace.timesMs,
        values=trace.values * scale + offset,
        source=f"{trace.source}|ha",
    )


def applyDm(trace: ShotTrace, channel: str) -> ShotTrace:
    """DM: ベースライン（先頭 5%）を引いた相対信号。"""
    values = trace.values.astype(np.float64, copy=True)
    nBase = max(1, int(len(values) * 0.05))
    baseline = float(np.mean(values[:nBase])) if len(values) else 0.0
    return ShotTrace(
        timesMs=trace.timesMs,
        values=values - baseline,
        source=f"{trace.source}|dm:{channel}",
    )


def applyNl(trace: ShotTrace, channel: str) -> ShotTrace:
    """NL: densityFactor * (phase - phaseOffset)。"""
    coefs = loadCoefMap("NL/nl_coef.txt")
    densityFactor, phaseOffset = coefs.get(channel, (1.0e17, 0.0))
    return ShotTrace(
        timesMs=trace.timesMs,
        values=(trace.values - phaseOffset) * densityFactor,
        source=f"{trace.source}|nl",
    )


def applyVcc(trace: ShotTrace, channel: str) -> ShotTrace:
    """VCC: そのまま（必要なら将来スケールを追加）。"""
    return ShotTrace(
        timesMs=trace.timesMs,
        values=trace.values,
        source=f"{trace.source}|vcc:{channel}",
    )


def processTrace(kind: str, channel: str, trace: ShotTrace) -> ShotTrace:
    """診断種別に応じた後処理を適用する。"""
    if kind == "Ha":
        return applyHa(trace, channel)
    if kind == "DM":
        return applyDm(trace, channel)
    if kind == "NL":
        return applyNl(trace, channel)
    if kind == "VCC":
        return applyVcc(trace, channel)
    return trace


def listLegacyCoefFiles(subdir: str) -> list[Path]:
    """校正ディレクトリ内の実ファイル一覧（README 除外）。"""
    directory = configRoot() / subdir
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.name.lower() not in {"readme.md", ".gitkeep"}
    )
