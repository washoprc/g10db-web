"""診断種別ごとの波形後処理。

TekeTekeKun の HaGraph / DMGraph / NLupGraph2 / VCCGraph 相当。
校正ファイルは config/Ha_coef と config/NL から読む。

主な仕様:
- Ha: bipolar CAMAC + calc_1/calc_2 合成係数（HaGraph.php）
- DM: DMC500/DMC600 ペアのリップル補正→積分（DMGraph.php）
- NL: 2 ポート atan2 位相アンラップ（NLupGraph2.php）
- VCC: bipolar CAMAC × camac_range/unit（VCCGraph.php）
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.services.configLoader import configRoot
from app.services.readshot import ShotTrace

# HaGraph.php の Camac_Range [mV]
HA_CAMAC_RANGE_MV = 5000.0

# VCCGraph.php / index.php の既定値
# index.php は camac_range=" 2e-5/(2.2)" を GET 文字列のまま渡し、
# PHP の数値変換では先頭の 2e-5 だけが使われる（/(2.2) は評価されない）。
VCC_BIT = 12
VCC_SAMP_MS = 1.0
VCC_TRIG_MS = 0.0
VCC_CAMAC_RANGE = 2.0e-5
VCC_UNIT = 1.0e-6

# DMGraph.php 定数（size は GET を無視して 4096 固定）
DM_MAX_ADC = 2 ** 11
DM_CAMAC_RANGE = 0.05
DM_SAMP_MS = 0.1
DM_SCALE = 1.0e5
DM_SAMPLE_COUNT = 4096


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
    for path in base.iterdir():
        if path.is_dir() and path.name.lower() == channel.lower():
            return path
    return None


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


def _readNameList(path: Path) -> list[str]:
    """1 行 1 ファイル名のリストを読む（空行・# 除外）。"""
    if not path.is_file():
        return []
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def _pickAt(values: list[float], index: int, fallback: float) -> float:
    """チャネルインデックスの値を取る（範囲外は末尾または fallback）。"""
    if not values:
        return fallback
    if index < 0:
        return values[0]
    if index >= len(values):
        return values[-1]
    return values[index]


def loadHaOffsetWindow(detectorDir: Path) -> tuple[float, int]:
    """offset.txt から (offset_1[ms], offset_2[samples]) を読む。

    HaGraph.php / create_detector_info 互換。2 行目が無い場合は点数 10。
    """
    path = detectorDir / "offset.txt"
    if not path.is_file():
        return (0.0, 10)
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    offset1 = 0.0
    offset2 = 10
    if lines:
        try:
            offset1 = float(lines[0].split()[0].replace(",", ""))
        except ValueError:
            offset1 = 0.0
    if len(lines) >= 2:
        try:
            offset2 = int(float(lines[1].split()[0].replace(",", "")))
        except ValueError:
            offset2 = 10
    if offset2 < 1:
        offset2 = 1
    return (offset1, offset2)


def buildHaChannelCoefs(
    detectorDir: Path,
    shotNo: int | None,
    channelCount: int,
) -> list[float]:
    """calc_1（積）/ calc_2（商）からチャネル係数を合成する。

    create_detector_info 相当: coef *= multi; coef /= div。
    """
    coefs = [1.0] * max(1, channelCount)
    for name in _readNameList(detectorDir / "calc_1.txt"):
        values = _readFitFloatRow(detectorDir / name, shotNo, fallback=1.0)
        for index in range(len(coefs)):
            coefs[index] *= _pickAt(values, index, 1.0)
    for name in _readNameList(detectorDir / "calc_2.txt"):
        values = _readFitFloatRow(detectorDir / name, shotNo, fallback=1.0)
        for index in range(len(coefs)):
            divisor = _pickAt(values, index, 1.0)
            if divisor == 0:
                divisor = 1.0
            coefs[index] /= divisor
    return coefs


@dataclass
class HaDetectorMeta:
    """HaGraph 用メタ（ショット適合済み）。"""

    detector: str
    ports: list[str]
    channelCoefs: list[float]
    offset1Ms: float
    offset2Samples: int
    bit: int
    sampMs: float
    trigMs: float
    chNumber: int


def loadHaDetectorMeta(detector: str, shotNo: int | None = None) -> HaDetectorMeta | None:
    """検出器ディレクトリから HaGraph 用メタを組み立てる。"""
    detectorDir = resolveHaDetectorDir(detector)
    if detectorDir is None:
        return None

    ports: list[str] = []
    portFile = detectorDir / "port.txt"
    if portFile.is_file():
        from app.services.portResolver import readFitShotRow

        rawPorts = readFitShotRow(portFile, shotNo) or []
        ports = [p for p in rawPorts if re.fullmatch(r"[A-Za-z0-9_]+", p)]

    chNumber = int(_readScalarFile(detectorDir / "ch_number.txt", float(len(ports) or 1)))
    if chNumber < 1:
        chNumber = max(1, len(ports) or 1)
    channelCoefs = buildHaChannelCoefs(detectorDir, shotNo, chNumber)
    offset1Ms, offset2Samples = loadHaOffsetWindow(detectorDir)
    bit = int(_readScalarFile(detectorDir / "bit.txt", 12))
    sampMs = _readScalarFile(detectorDir / "samp.txt", 1.0)
    trigMs = _readScalarFile(detectorDir / "trig.txt", 0.0)

    return HaDetectorMeta(
        detector=detectorDir.name,
        ports=ports,
        channelCoefs=channelCoefs,
        offset1Ms=offset1Ms,
        offset2Samples=offset2Samples,
        bit=bit if bit > 0 else 12,
        sampMs=sampMs if sampMs > 0 else 1.0,
        trigMs=trigMs,
        chNumber=chNumber,
    )


def applyHaCamac(
    trace: ShotTrace,
    meta: HaDetectorMeta,
    channelIndex: int = 0,
) -> ShotTrace:
    """HaGraph.php 式で CAMAC 生データを物理量へ変換する。

    val = (data - max - baseline) / max * Camac_Range * coef
    baseline は offset_1〜offset_2 窓の (data-max) 平均。
    """
    coef = _pickAt(meta.channelCoefs, channelIndex, 1.0)
    maxAdc = float(2 ** (meta.bit - 1))
    if maxAdc <= 0:
        maxAdc = 2048.0
    raw = trace.values.astype(np.float64, copy=False)
    n = len(raw)
    osFirst = int((meta.offset1Ms - meta.trigMs) / meta.sampMs)
    if osFirst < 0:
        osFirst = 0
    osLast = osFirst + meta.offset2Samples
    # 窓がデータ外（短いテストデータ等）なら先頭サンプルで代替
    if n == 0:
        baseline = 0.0
    elif osFirst >= n:
        osFirst = 0
        osLast = min(meta.offset2Samples, n)
        baseline = float(np.mean(raw[osFirst:osLast] - maxAdc))
    else:
        osLast = min(osLast, n)
        if osLast <= osFirst:
            baseline = 0.0
        else:
            baseline = float(np.mean(raw[osFirst:osLast] - maxAdc))
    if not math.isfinite(baseline):
        baseline = 0.0
    values = (raw - maxAdc - baseline) / maxAdc * HA_CAMAC_RANGE_MV * coef
    times = meta.trigMs + np.arange(n, dtype=np.float64) * meta.sampMs
    return ShotTrace(
        timesMs=times,
        values=values,
        source=(
            f"{trace.source}|ha-camac:{meta.detector}:ch{channelIndex}"
            f":coef={coef}:bg={baseline}"
        ),
    )


def applyHa(trace: ShotTrace, channel: str, shotNo: int | None = None) -> ShotTrace:
    """Ha: 検出器メタがあれば HaGraph 式、無ければレガシー簡易変換。"""
    if trace.source.startswith("legacy-camac"):
        meta = loadHaDetectorMeta(channel, shotNo)
        if meta is not None:
            return applyHaCamac(trace, meta, channelIndex=0)

    detectorDir = resolveHaDetectorDir(channel)
    if detectorDir is None:
        coefs = loadCoefMap("Ha_coef/ha_coef.txt")
        scale, offset = coefs.get(channel, (1.0, 0.0))
        return ShotTrace(
            timesMs=trace.timesMs,
            values=trace.values * scale + offset,
            source=f"{trace.source}|ha-legacy",
        )

    meta = loadHaDetectorMeta(channel, shotNo)
    if meta is not None and trace.source.startswith("legacy-camac"):
        return applyHaCamac(trace, meta, channelIndex=0)
    scale = _pickAt(meta.channelCoefs, 0, 1.0) if meta else 1.0
    return ShotTrace(
        timesMs=trace.timesMs,
        values=trace.values * scale,
        source=f"{trace.source}|ha:{channel}:s={scale}",
    )


def applyDmPair(trace1: ShotTrace, trace2: ShotTrace) -> ShotTrace:
    """DMGraph.php 相当: 2 ポートから反磁性信号を復元する。

    1. bipolar CAMAC（max=2^11, range=0.05）
    2. ripple = v2 - v1、50ms 窓で ratio 推定
    3. db/dt = v1 - ratio*ripple → 平均除去 → 積分
    4. t=50ms 付近でオフセット除去、×1e5

    読み点数は DMGraph.php と同じく先頭 4096 点に制限する
    （実ファイルは 5120 点などより長いことがある）。
    """
    n = min(len(trace1.values), len(trace2.values), DM_SAMPLE_COUNT)
    if n < 8:
        raise ValueError(
            f"applyDmPair: too few samples n={n} "
            f"src1={trace1.source} src2={trace2.source}"
        )
    maxAdc = float(DM_MAX_ADC)
    v1 = (trace1.values[:n].astype(np.float64) - maxAdc) / maxAdc * DM_CAMAC_RANGE
    v2 = (trace2.values[:n].astype(np.float64) - maxAdc) / maxAdc * DM_CAMAC_RANGE
    ripple = v2 - v1

    window = int(50.0 / DM_SAMP_MS)
    window = max(1, min(window, n))
    ratioSum = 0.0
    ratioCount = 0
    for index in range(window):
        if ripple[index] != 0.0:
            ratioSum += float(v1[index] / ripple[index])
            ratioCount += 1
    ratio = ratioSum / ratioCount if ratioCount > 0 else 0.0

    dbdt = v1 - ratio * ripple
    dbdt = dbdt - float(np.mean(dbdt))
    dm = np.cumsum(dbdt) * DM_SAMP_MS * 0.001

    osFirst = int(50.0 / DM_SAMP_MS)
    osLast = min(n, osFirst + 5)
    if osFirst >= n:
        osFirst = 0
        osLast = min(5, n)
    offset = float(np.mean(dm[osFirst:osLast]))
    values = (dm - offset) * DM_SCALE
    times = np.arange(n, dtype=np.float64) * DM_SAMP_MS
    return ShotTrace(
        timesMs=times,
        values=values,
        source=f"{trace1.source}+{trace2.source}|dm-pair:ratio={ratio}",
    )


def applyDm(trace: ShotTrace, channel: str) -> ShotTrace:
    """単ポート DM（フォールバック）。ペア処理が本流。"""
    values = trace.values.astype(np.float64, copy=True)
    nBase = max(1, int(len(values) * 0.05))
    baseline = float(np.mean(values[:nBase])) if len(values) else 0.0
    return ShotTrace(
        timesMs=trace.timesMs,
        values=values - baseline,
        source=f"{trace.source}|dm-single:{channel}",
    )


def parseNlConfig(path: Path) -> dict[str, float | str]:
    """NL*.txt のパーサ（NLupGraph2 / index.php NL2ch 行順）。

    0:title, 1:chA, 2:chB, 3:dt, 4:bit, 5:trig, 6:ymin, 7:ymax, 8:size
    """
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
            meta["dt"] = 0.02
    if len(lines) >= 5:
        try:
            meta["bit"] = float(lines[4])
        except ValueError:
            meta["bit"] = 12.0
    if len(lines) >= 6:
        try:
            meta["trig"] = float(lines[5])
        except ValueError:
            meta["trig"] = 50.0
    if len(lines) >= 9:
        try:
            meta["size"] = float(lines[8])
        except ValueError:
            pass
    return meta


def loadNlConfig(channel: str) -> dict[str, float | str]:
    """チャネル名に対応する NL 設定を返す。"""
    nlDir = configRoot() / "NL"
    if not nlDir.is_dir():
        return {}
    candidates: list[Path] = []
    for name in (f"{channel}.txt", channel, f"{channel}.TXT"):
        path = nlDir / name
        if path.is_file():
            candidates.append(path)
    if not candidates:
        candidates = sorted(nlDir.glob(f"{channel}*.txt"))
    for path in candidates:
        if path.name.lower() == "readme.md":
            continue
        return parseNlConfig(path)
    return {}


# NLupGraph2.php は for ($i=0; $i<=10000; $i++) のため、
# dt=0.02 / trig=50 だと時刻上限は約 250 ms。
NL_PHP_LOOP_MAX = 10001


def applyNlPair(
    trace1: ShotTrace,
    trace2: ShotTrace,
    *,
    sampMs: float = 0.02,
    trigMs: float = 50.0,
    bit: int = 12,
) -> ShotTrace:
    """NLupGraph2.php 相当: atan2 位相アンラップ → 線密度。

    values = unwrap(atan2(ch1, ch2)) * 5.2 / (2π) - bias
    ループ上限は PHP と同じ 10001 点（≈250 ms @ 0.02 ms）。
    """
    n = min(len(trace1.values), len(trace2.values), NL_PHP_LOOP_MAX)
    if n < 8:
        raise ValueError(
            f"applyNlPair: too few samples n={n} "
            f"src1={trace1.source} src2={trace2.source}"
        )
    maxAdc = float(2 ** (bit - 1))
    x = trace1.values[:n].astype(np.float64) - maxAdc
    y = trace2.values[:n].astype(np.float64) - maxAdc
    phase = np.arctan2(x, y)
    # 符号変化 + |phase|>2 で 2π 巻き戻し（PHP と同じ）
    unwrapped = np.empty(n, dtype=np.float64)
    kuri = 0
    prev = float(phase[0])
    unwrapped[0] = prev
    for index in range(1, n):
        sc = float(phase[index])
        if prev * sc < 0.0:
            if sc < -2.0:
                kuri += 1
            elif sc > 2.0:
                kuri -= 1
        prev = sc
        unwrapped[index] = sc + kuri * 2.0 * math.pi
    values = unwrapped * 5.2 / (2.0 * math.pi)
    values = values - float(values[0])
    times = trigMs + np.arange(n, dtype=np.float64) * sampMs
    return ShotTrace(
        timesMs=times,
        values=values,
        source=f"{trace1.source}+{trace2.source}|nl-pair:atan2",
    )


def applyNl(trace: ShotTrace, channel: str) -> ShotTrace:
    """単ポート NL フォールバック（位相復元不可時）。"""
    return ShotTrace(
        timesMs=trace.timesMs,
        values=trace.values.astype(np.float64, copy=False),
        source=f"{trace.source}|nl-single:{channel}",
    )


def applyVcc(trace: ShotTrace, channel: str) -> ShotTrace:
    """VCCGraph.php 相当: bipolar CAMAC × camac_range / unit。"""
    maxAdc = float(2 ** (VCC_BIT - 1))
    scale = VCC_CAMAC_RANGE / VCC_UNIT
    raw = trace.values.astype(np.float64, copy=False)
    values = (raw - maxAdc) / maxAdc * scale
    n = len(values)
    times = VCC_TRIG_MS + np.arange(n, dtype=np.float64) * VCC_SAMP_MS
    return ShotTrace(
        timesMs=times,
        values=values,
        source=f"{trace.source}|vcc:{channel}:scale={scale}",
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
    """診断種別に応じた単トレース後処理（Ha / VCC / フォールバック）。"""
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
