"""診断種別ごとの波形後処理。

TekeTekeKun の HaGraph / DMGraph / NLupGraph2 / VCCGraph 相当。
校正ファイルは config/Ha_coef と config/NL から読む。
レガシー CAMAC 由来の Ha は HaGraph 式（Intensity=Data*coef*const/(amp*glass_trans)-BG）を適用。
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.services.configLoader import configRoot
from app.services.readshot import ShotTrace


def loadCoefMap(relativePath: str) -> dict[str, tuple[float, float]]:
    """`channel scale offset` 形式の校正ファイルを読む（レガシー簡易形式）。"""
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


def resolveHaDetectorDir(channel: str) -> Path | None:
    """Ha 検出器ディレクトリを解決する（HaCT / HaEB 等）。"""
    base = configRoot() / "Ha_coef"
    if not base.is_dir():
        return None
    direct = base / channel
    if direct.is_dir():
        return direct
    # 大小文字ゆれ
    for path in base.iterdir():
        if path.is_dir() and path.name.lower() == channel.lower():
            return path
    return None


def loadHaShotCoefs(detectorDir: Path) -> list[tuple[int, list[float]]]:
    """coef.txt を [(shotNo, [c1,c2,...]), ...] として読む（昇順）。"""
    coefFile = detectorDir / "coef.txt"
    if not coefFile.is_file():
        return []
    rows: list[tuple[int, list[float]]] = []
    text = coefFile.read_text(encoding="utf-8", errors="ignore")
    reader = csv.reader(text.splitlines())
    for parts in reader:
        if not parts:
            continue
        head = parts[0].strip().lower()
        if head in {"shot_no", "shotno", "shot"}:
            continue
        try:
            shotNo = int(float(parts[0]))
            coeffs = [float(x) for x in parts[1:] if str(x).strip() != ""]
        except ValueError:
            continue
        if coeffs:
            rows.append((shotNo, coeffs))
    rows.sort(key=lambda item: item[0])
    return rows


def pickHaCoefsForShot(detectorDir: Path, shotNo: int | None) -> list[float]:
    """ショット番号に対応する係数行を選ぶ（以下で最大の shot_no）。"""
    rows = loadHaShotCoefs(detectorDir)
    if not rows:
        return [1.0]
    if shotNo is None:
        return rows[-1][1]
    chosen = rows[0][1]
    for threshold, coeffs in rows:
        if shotNo >= threshold:
            chosen = coeffs
        else:
            break
    return chosen


def _readFitFloatRow(path: Path, shotNo: int | None, fallback: float = 1.0) -> list[float]:
    """shot_no 付き CSV から float 行を選ぶ（無ければ [fallback]）。"""
    if not path.is_file():
        return [fallback]
    rows: list[tuple[int, list[float]]] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    reader = csv.reader(text.splitlines())
    for parts in reader:
        if not parts:
            continue
        head = parts[0].strip().lower()
        if head in {"shot_no", "shotno", "shot"}:
            continue
        try:
            rowShot = int(float(parts[0]))
            values = [float(x) for x in parts[1:] if str(x).strip() != ""]
        except ValueError:
            continue
        if values:
            rows.append((rowShot, values))
    if not rows:
        return [fallback]
    rows.sort(key=lambda item: item[0])
    if shotNo is None:
        return rows[-1][1]
    chosen = rows[0][1]
    for threshold, values in rows:
        if shotNo >= threshold:
            chosen = values
        else:
            break
    return chosen


def _readScalarFile(path: Path, fallback: float) -> float:
    """1 行目の先頭数値を読む。"""
    if not path.is_file():
        return fallback
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            return float(line.split()[0].replace(",", ""))
        except ValueError:
            continue
    return fallback


def loadHaOffset(detectorDir: Path) -> float:
    """offset.txt の先頭値を返す。"""
    return _readScalarFile(detectorDir / "offset.txt", 0.0)


@dataclass
class HaDetectorMeta:
    """HaGraph 用メタ（ショット適合済み）。"""

    detector: str
    ports: list[str]
    coefs: list[float]
    consts: list[float]
    amps: list[float]
    glassTrans: list[float]
    offset: float
    bit: int
    sampMs: float
    trigMs: float
    chNumber: int


def loadHaDetectorMeta(detector: str, shotNo: int | None = None) -> HaDetectorMeta | None:
    """検出器ディレクトリから HaGraph 用メタを組み立てる。"""
    detectorDir = resolveHaDetectorDir(detector)
    if detectorDir is None:
        return None

    # port は文字列行
    ports: list[str] = []
    portFile = detectorDir / "port.txt"
    if portFile.is_file():
        from app.services.portResolver import readFitShotRow

        rawPorts = readFitShotRow(portFile, shotNo) or []
        ports = [p for p in rawPorts if re.fullmatch(r"[A-Za-z0-9_]+", p)]

    coefs = pickHaCoefsForShot(detectorDir, shotNo)
    consts = _readFitFloatRow(detectorDir / "const.txt", shotNo, fallback=1.0)
    amps = _readFitFloatRow(detectorDir / "amp.txt", shotNo, fallback=1.0)
    glassTrans = _readFitFloatRow(detectorDir / "glass_trans.txt", shotNo, fallback=1.0)
    offset = loadHaOffset(detectorDir)
    bit = int(_readScalarFile(detectorDir / "bit.txt", 12))
    sampMs = _readScalarFile(detectorDir / "samp.txt", 1.0)
    trigMs = _readScalarFile(detectorDir / "trig.txt", 0.0)
    chNumber = int(_readScalarFile(detectorDir / "ch_number.txt", float(len(ports) or 1)))

    return HaDetectorMeta(
        detector=detectorDir.name,
        ports=ports,
        coefs=coefs,
        consts=consts,
        amps=amps,
        glassTrans=glassTrans,
        offset=offset,
        bit=bit,
        sampMs=sampMs if sampMs > 0 else 1.0,
        trigMs=trigMs,
        chNumber=chNumber,
    )


def _pickAt(values: list[float], index: int, fallback: float) -> float:
    """チャネルインデックスの値を取る（範囲外は末尾または fallback）。"""
    if not values:
        return fallback
    if index < 0:
        return values[0]
    if index >= len(values):
        return values[-1]
    return values[index]


def applyHaCamac(
    trace: ShotTrace,
    meta: HaDetectorMeta,
    channelIndex: int = 0,
) -> ShotTrace:
    """HaGraph 式で CAMAC 生データを物理量へ変換する。

    Intensity = Data * coef * const / (amp * glass_trans) - BG
    時間軸は samp / trig に合わせて再構築する。
    """
    coef = _pickAt(meta.coefs, channelIndex, 1.0)
    const = _pickAt(meta.consts, channelIndex, 1.0)
    amp = _pickAt(meta.amps, channelIndex, 1.0)
    glass = _pickAt(meta.glassTrans, channelIndex, 1.0)
    denom = amp * glass
    if denom == 0:
        denom = 1.0
    scale = (coef * const) / denom
    values = trace.values.astype(np.float64, copy=False) * scale - meta.offset
    n = len(values)
    times = meta.trigMs + np.arange(n, dtype=np.float64) * meta.sampMs
    return ShotTrace(
        timesMs=times,
        values=values,
        source=f"{trace.source}|ha-camac:{meta.detector}:ch{channelIndex}:s={scale}",
    )


def applyHa(trace: ShotTrace, channel: str, shotNo: int | None = None) -> ShotTrace:
    """Ha: 検出器ディレクトリの coef/offset を適用。

    ソースが legacy-camac のときは HaGraph 式（applyHaCamac）を使う。
    それ以外は先頭係数 × 値 + offset の簡易変換。
    """
    if trace.source.startswith("legacy-camac"):
        meta = loadHaDetectorMeta(channel, shotNo)
        if meta is not None:
            return applyHaCamac(trace, meta, channelIndex=0)

    detectorDir = resolveHaDetectorDir(channel)
    if detectorDir is None:
        # レガシー flat 形式
        coefs = loadCoefMap("Ha_coef/ha_coef.txt")
        scale, offset = coefs.get(channel, (1.0, 0.0))
        return ShotTrace(
            timesMs=trace.timesMs,
            values=trace.values * scale + offset,
            source=f"{trace.source}|ha-legacy",
        )

    coeffs = pickHaCoefsForShot(detectorDir, shotNo)
    scale = float(coeffs[0]) if coeffs else 1.0
    offset = loadHaOffset(detectorDir)
    return ShotTrace(
        timesMs=trace.timesMs,
        values=trace.values * scale + offset,
        source=f"{trace.source}|ha:{detectorDir.name}:s={scale}",
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


def parseNlConfig(path: Path) -> dict[str, float | str]:
    """NL*.txt の簡易パーサ（行順: title, chA, chB, dt, ...）。"""
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    ]
    meta: dict[str, float | str] = {"path": path.name}
    if len(lines) >= 1:
        meta["title"] = lines[0]
    if len(lines) >= 2:
        meta["channelA"] = lines[1]
    if len(lines) >= 3:
        meta["channelB"] = lines[2]
    if len(lines) >= 4:
        try:
            meta["dt"] = float(lines[3])
        except ValueError:
            pass
    # 末尾付近の数値を densityFactor 候補として使う
    for line in reversed(lines):
        try:
            meta["densityFactor"] = float(line)
            break
        except ValueError:
            continue
    return meta


def applyNl(trace: ShotTrace, channel: str) -> ShotTrace:
    """NL: NL 設定ファイルの係数を適用。"""
    nlDir = configRoot() / "NL"
    meta: dict[str, float | str] = {}
    if nlDir.is_dir():
        # チャネル名に一致するファイルを優先
        candidates = list(nlDir.glob(f"{channel}*.txt")) + list(nlDir.glob("*.txt"))
        for path in candidates:
            if path.name.lower() == "readme.md":
                continue
            meta = parseNlConfig(path)
            break

    rawFactor = float(meta.get("densityFactor", 1.0))  # type: ignore[arg-type]
    # サンプル数（例: 12288）など大きすぎる整数は係数に使わない
    densityFactor = rawFactor if 0 < rawFactor < 1000 else 1.0
    return ShotTrace(
        timesMs=trace.timesMs,
        values=trace.values * densityFactor,
        source=f"{trace.source}|nl:{meta.get('path', '')}",
    )


def applyVcc(trace: ShotTrace, channel: str) -> ShotTrace:
    """VCC: そのまま（必要なら将来スケールを追加）。"""
    return ShotTrace(
        timesMs=trace.timesMs,
        values=trace.values,
        source=f"{trace.source}|vcc:{channel}",
    )


def processTrace(
    kind: str,
    channel: str,
    trace: ShotTrace,
    shotNo: int | None = None,
    *,
    channelIndex: int = 0,
    haMeta: HaDetectorMeta | None = None,
) -> ShotTrace:
    """診断種別に応じた後処理を適用する。"""
    if kind == "Ha":
        if haMeta is not None and trace.source.startswith("legacy-camac"):
            return applyHaCamac(trace, haMeta, channelIndex=channelIndex)
        return applyHa(trace, channel, shotNo=shotNo)
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
        for p in directory.rglob("*")
        if p.is_file() and p.name.lower() not in {"readme.md", ".gitkeep"}
    )
