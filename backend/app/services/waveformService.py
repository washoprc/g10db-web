"""波形取得サービス（Ha / DM / NL / VCC）。

処理順:
1. DATA_ROOT / ftp_cache 上のローカル・ポートファイル
2. FTP 取得（kasumi: `/usr2/shot/{shot}/{port}`）→ readshot パース → 診断後処理
3. デモ合成波形（USE_DEMO=1、または USE_DEMO=0 で FTP 失敗時は note 付き）

任意 SQL は使わない。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np

from app.config import getSettings
from app.db import fetchAll
from app.models.schemas import (
    WaveformKind,
    WaveformPoint,
    WaveformResponse,
    WaveformSeries,
)
from app.services import ftpClient
from app.services.configLoader import loadGroupList, loadTableList
from app.services.portResolver import resolvePorts
from app.services.processors import (
    applyDmPair,
    applyNlPair,
    loadHaDetectorMeta,
    loadNlConfig,
    processTrace,
)
from app.services.readshot import ShotTrace, parseReadshot

logger = logging.getLogger(__name__)

# TekeTekeKun/index.php 相当の時間窓
DEFAULT_START_MS = 50.0
DEFAULT_END_MS_SHORT = 250.0
DEFAULT_END_MS_LONG = 400.0
LONG_PULSE_THRESHOLD_MS = 300.0


def resolveTimeWindow(shotNo: int) -> tuple[float, float]:
    """ショットの表示時間窓 (startMs, endMs) を返す。

    TekeTekeKun 相当:
    - start = 50
    - short pulse (gp3.time_e ≤ 300): end = 250
    - long pulse (gp3.time_e > 300): end = 400（表示上限。time_e 自体は使わない）
    """
    startMs = DEFAULT_START_MS
    endMs = DEFAULT_END_MS_LONG
    settings = getSettings()
    if settings.useDemo:
        return startMs, endMs
    try:
        rows = fetchAll(
            "SELECT time_e FROM gp3 WHERE shotno = %s LIMIT 1",
            (shotNo,),
        )
        if rows and rows[0].get("time_e") is not None:
            mode = float(rows[0]["time_e"])
            if mode > LONG_PULSE_THRESHOLD_MS:
                endMs = DEFAULT_END_MS_LONG
            else:
                endMs = DEFAULT_END_MS_SHORT
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "resolveTimeWindow(shotNo=%s) failed: %s — using %.0f–%.0f",
            shotNo,
            exc,
            startMs,
            endMs,
        )
    # 表示は 400 ms を超えない
    endMs = min(float(endMs), DEFAULT_END_MS_LONG)
    if endMs <= startMs:
        endMs = DEFAULT_END_MS_LONG
    return startMs, endMs


def buildMissingDataNote(
    shotNo: int,
    kind: WaveformKind,
    detail: str | None = None,
) -> str:
    """実データが無いときの説明文（偽デモ波形は出さない）。"""
    settings = getSettings()
    remoteDir = f"{settings.ftpBasePath.rstrip('/')}/{shotNo}"
    shotOk = ftpClient.shotDirExists(shotNo) if ftpClient.isFtpConfigured() else None
    if settings.useDemo:
        return (
            f"Shot {shotNo} {kind}: USE_DEMO=1 のためデモ波形です。"
            " 実データは USE_DEMO=0 と FTP_* を設定してください。"
        )
    if not ftpClient.isFtpConfigured():
        return (
            f"Shot {shotNo} {kind}: FTP 未設定のため波形を取得できません。"
            f" Host={settings.ftpHost or '(none)'}。"
        )
    if shotOk is False:
        return (
            f"Shot {shotNo} {kind}: FTP 上にショットディレクトリがありません"
            f"（{remoteDir}）。kasumi に未保存のショットの可能性があります。"
        )
    parts = [
        f"Shot {shotNo} {kind}: ポートファイルの取得または解析に失敗しました。",
        f"Remote={remoteDir}/{{port}}。",
    ]
    if detail:
        parts.append(detail)
    return " ".join(parts)


def buildFallbackNote(
    shotNo: int,
    kind: WaveformKind,
    detail: str | None = None,
) -> str:
    """互換エイリアス（欠測メッセージ）。"""
    return buildMissingDataNote(shotNo, kind, detail)


def resolveKindMeta(kind: WaveformKind) -> dict[str, str]:
    """診断種別の表示メタ情報。"""
    defaults = {
        "Ha": {"label": "Hα", "unit": "uW/cm^2sr"},
        "DM": {"label": "Diamagnetism", "unit": "1E-5 wb"},
        "NL": {"label": "Line density", "unit": "1E13cm-2"},
        "VCC": {"label": "VCC", "unit": "1E-6 torr"},
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
        "Ha": ["HaCT", "HaEB", "HaWB", "Hachinosu", "Dorami", "CT25", "HaIMT"],
        "DM": ["DM_CC"],
        "NL": ["NLCCNEW", "NLEBNEW"],
        "VCC": ["VCC1"],
    }
    return fallback[kind]


def ftpDirFor(kind: WaveformKind) -> str:
    """互換用: 旧サブディレクトリ名（kasumi 本番パスでは未使用）。"""
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


def findLocalPortFile(shotNo: int, portName: str) -> Path | None:
    """DATA_ROOT / ftp_cache 上のポートファイルを探す（拡張子なし優先）。"""
    if not portName:
        return None
    root = getSettings().dataRoot
    candidates = [
        root / "ftp_cache" / str(shotNo) / portName,
        root / str(shotNo) / portName,
        root / "ftp_cache" / str(shotNo) / f"{portName}.dat",
        root / str(shotNo) / f"{portName}.dat",
    ]
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def findLocalChannelFiles(shotNo: int, kind: WaveformKind, channel: str) -> list[Path]:
    """DATA_ROOT 配下の旧レイアウト候補パスを列挙する。"""
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


def _seriesFromTrace(
    name: str,
    unit: str,
    processed,
) -> WaveformSeries | None:
    """後処理済みトレースから WaveformSeries を作る。"""
    points = [
        WaveformPoint(t=float(t), v=float(v))
        for t, v in zip(processed.timesMs, processed.values, strict=True)
        if math.isfinite(float(t)) and math.isfinite(float(v))
    ]
    if not points:
        return None
    return WaveformSeries(name=name, unit=unit, points=points)


def _ensurePortsFetched(shotNo: int, portNames: list[str]) -> None:
    """未キャッシュのポートを FTP で一括取得する。"""
    needed = [
        port
        for port in portNames
        if port and findLocalPortFile(shotNo, port) is None
    ]
    if needed and ftpClient.isFtpConfigured() and not getSettings().useDemo:
        ftpClient.fetchPortFiles(shotNo, needed)


def _loadPortTrace(
    shotNo: int,
    port: str,
    *,
    defaultDtMs: float = 1.0,
) -> ShotTrace | None:
    """ポートファイルを全点読みする（後処理側で時間軸・窓を決める）。"""
    path = findLocalPortFile(shotNo, port)
    if path is None and ftpClient.isFtpConfigured() and not getSettings().useDemo:
        path = ftpClient.fetchPortFile(shotNo, port)
    if path is None:
        return None
    return parseReadshot(
        path,
        startMs=-1e9,
        endMs=1e9,
        defaultDtMs=defaultDtMs,
    )


def _windowTrace(trace: ShotTrace, startMs: float, endMs: float) -> ShotTrace:
    """時間窓で切り出す。"""
    if endMs <= startMs:
        endMs = startMs + 200.0
    mask = (trace.timesMs >= startMs) & (trace.timesMs <= endMs)
    return ShotTrace(
        timesMs=trace.timesMs[mask],
        values=trace.values[mask],
        source=trace.source,
    )


def _loadHaSeries(
    shotNo: int,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries]:
    """Ha: 検出器ごとのポートを HaGraph 式で変換する。"""
    meta = resolveKindMeta("Ha")
    series: list[WaveformSeries] = []
    names = channelNamesFor("Ha")
    allPorts: list[str] = []
    for name in names:
        allPorts.extend(resolvePorts("Ha", name, shotNo))
    _ensurePortsFetched(shotNo, allPorts)

    for name in names:
        ports = resolvePorts("Ha", name, shotNo)
        haMeta = loadHaDetectorMeta(name, shotNo)
        defaultDt = haMeta.sampMs if haMeta is not None else 1.0
        if not ports:
            files = findLocalChannelFiles(shotNo, "Ha", name)
            if not files:
                continue
            trace = parseReadshot(files[0], startMs=-1e9, endMs=1e9, defaultDtMs=defaultDt)
            if trace is None or len(trace.values) == 0:
                continue
            processed = processTrace("Ha", name, trace, shotNo=shotNo, haMeta=haMeta)
            item = _seriesFromTrace(name, meta["unit"], _windowTrace(processed, startMs, endMs))
            if item:
                series.append(item)
            continue

        for channelIndex, port in enumerate(ports):
            trace = _loadPortTrace(shotNo, port, defaultDtMs=defaultDt)
            if trace is None or len(trace.values) == 0:
                continue
            processed = processTrace(
                "Ha",
                name,
                trace,
                shotNo=shotNo,
                channelIndex=channelIndex,
                haMeta=haMeta,
            )
            seriesName = f"{name}:{port}" if len(ports) > 1 else name
            item = _seriesFromTrace(
                seriesName,
                meta["unit"],
                _windowTrace(processed, startMs, endMs),
            )
            if item:
                series.append(item)
    return series


def _loadDmSeries(
    shotNo: int,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries]:
    """DM: DMC500+DMC600 ペアを DMGraph 式で 1 本にする。"""
    meta = resolveKindMeta("DM")
    ports = resolvePorts("DM", "DM_CC", shotNo)
    if len(ports) < 2:
        return []
    _ensurePortsFetched(shotNo, ports)
    trace1 = _loadPortTrace(shotNo, ports[0], defaultDtMs=0.1)
    trace2 = _loadPortTrace(shotNo, ports[1], defaultDtMs=0.1)
    if trace1 is None or trace2 is None:
        return []
    try:
        processed = applyDmPair(trace1, trace2)
    except ValueError as exc:
        logger.warning("DM pair failed shot=%s: %s", shotNo, exc)
        return []
    item = _seriesFromTrace("DMCC", meta["unit"], _windowTrace(processed, startMs, endMs))
    return [item] if item else []


def _loadNlSeries(
    shotNo: int,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries]:
    """NL: 各チャネルの 2 ポートを NLupGraph2 式で変換する。"""
    meta = resolveKindMeta("NL")
    series: list[WaveformSeries] = []
    names = channelNamesFor("NL")
    allPorts: list[str] = []
    for name in names:
        allPorts.extend(resolvePorts("NL", name, shotNo))
    _ensurePortsFetched(shotNo, allPorts)

    for name in names:
        ports = resolvePorts("NL", name, shotNo)
        if len(ports) < 2:
            continue
        nlMeta = loadNlConfig(name)
        sampMs = float(nlMeta.get("dt", 0.02) or 0.02)  # type: ignore[arg-type]
        trigMs = float(nlMeta.get("trig", 50.0) or 50.0)  # type: ignore[arg-type]
        bit = int(float(nlMeta.get("bit", 12) or 12))  # type: ignore[arg-type]
        if sampMs <= 0:
            sampMs = 0.02
        trace1 = _loadPortTrace(shotNo, ports[0], defaultDtMs=sampMs)
        trace2 = _loadPortTrace(shotNo, ports[1], defaultDtMs=sampMs)
        if trace1 is None or trace2 is None:
            continue
        try:
            processed = applyNlPair(
                trace1,
                trace2,
                sampMs=sampMs,
                trigMs=trigMs,
                bit=bit,
            )
        except ValueError as exc:
            logger.warning("NL pair failed shot=%s channel=%s: %s", shotNo, name, exc)
            continue
        item = _seriesFromTrace(name, meta["unit"], _windowTrace(processed, startMs, endMs))
        if item:
            series.append(item)
    return series


def _loadVccSeries(
    shotNo: int,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries]:
    """VCC: VCCC00 を VCCGraph 式で 1 本にする。"""
    meta = resolveKindMeta("VCC")
    ports = resolvePorts("VCC", "VCC1", shotNo)
    if not ports:
        return []
    _ensurePortsFetched(shotNo, ports)
    trace = _loadPortTrace(shotNo, ports[0], defaultDtMs=1.0)
    if trace is None or len(trace.values) == 0:
        return []
    processed = processTrace("VCC", "VCC1", trace, shotNo=shotNo)
    item = _seriesFromTrace("VCCC00", meta["unit"], _windowTrace(processed, startMs, endMs))
    return [item] if item else []


def loadProcessedSeries(
    shotNo: int,
    kind: WaveformKind,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries] | None:
    """ローカル／FTP からポートを読み、後処理して返す。"""
    if kind == "Ha":
        series = _loadHaSeries(shotNo, startMs, endMs)
    elif kind == "DM":
        series = _loadDmSeries(shotNo, startMs, endMs)
    elif kind == "NL":
        series = _loadNlSeries(shotNo, startMs, endMs)
    elif kind == "VCC":
        series = _loadVccSeries(shotNo, startMs, endMs)
    else:
        series = []
    return series if series else None


def getWaveform(
    shotNo: int,
    kind: WaveformKind,
    startMs: float | None = None,
    endMs: float | None = None,
) -> WaveformResponse:
    """指定ショット・診断の波形を返す。

    start/end 未指定時は TekeTekeKun 相当（50–gp3.time_e または 50–250）。
    """
    resolvedStart, resolvedEnd = resolveTimeWindow(shotNo)
    if startMs is None:
        startMs = resolvedStart
    if endMs is None:
        endMs = resolvedEnd

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

    # USE_DEMO=1 のときだけ合成波形。本番設定では空系列 + 理由を返す。
    if settings.useDemo:
        return WaveformResponse(
            shotNo=shotNo,
            kind=kind,
            startMs=startMs,
            endMs=endMs,
            series=demoSeries(kind, startMs, endMs),
            demoMode=True,
            note=buildMissingDataNote(shotNo, kind),
        )

    return WaveformResponse(
        shotNo=shotNo,
        kind=kind,
        startMs=startMs,
        endMs=endMs,
        series=[],
        demoMode=False,
        note=buildMissingDataNote(shotNo, kind),
    )


def waveformRuntimeStatus() -> dict[str, object]:
    """波形ランタイムの設定・FTP 接続状態。"""
    settings = getSettings()
    ftp = ftpClient.ftpConfigStatus()
    if ftpClient.isFtpConfigured():
        probe = ftpClient.probeFtpConnection()
    else:
        probe = {"ok": False, "error": "FTP host/user not configured"}
    return {
        "useDemo": settings.useDemo,
        "ftp": ftp,
        "ftpProbe": probe,
        "dataRoot": str(settings.dataRoot),
        "configRoot": str(settings.configRoot),
        "ftpBasePath": settings.ftpBasePath,
    }


def diagnoseWaveform(
    shotNo: int,
    kind: WaveformKind,
    startMs: float | None = None,
    endMs: float | None = None,
) -> dict[str, object]:
    """ショット波形の取得・パース診断（デモバッジ原因調査用）。"""
    resolvedStart, resolvedEnd = resolveTimeWindow(shotNo)
    if startMs is None:
        startMs = resolvedStart
    if endMs is None:
        endMs = resolvedEnd
    settings = getSettings()
    names = channelNamesFor(kind)
    ports: dict[str, list[str]] = {}
    allPorts: list[str] = []
    for name in names:
        resolved = resolvePorts(kind, name, shotNo)
        ports[name] = resolved
        for port in resolved:
            if port not in allPorts:
                allPorts.append(port)

    fetchResults: dict[str, dict[str, object]] = {}
    parseResults: dict[str, dict[str, object]] = {}

    for port in allPorts:
        path = findLocalPortFile(shotNo, port)
        fetchedViaFtp = False
        if path is None and ftpClient.isFtpConfigured() and not settings.useDemo:
            path = ftpClient.fetchPortFile(shotNo, port)
            fetchedViaFtp = path is not None
        if path is None:
            fetchResults[port] = {
                "ok": False,
                "path": None,
                "viaFtp": False,
                "error": "not found locally and FTP miss/skipped",
            }
            parseResults[port] = {
                "ok": False,
                "source": None,
                "nPoints": 0,
                "error": "no file",
            }
            continue

        fetchResults[port] = {
            "ok": True,
            "path": str(path),
            "size": path.stat().st_size,
            "viaFtp": fetchedViaFtp,
        }
        try:
            trace = parseReadshot(path, startMs=startMs, endMs=endMs)
            if trace is None or len(trace.values) == 0:
                parseResults[port] = {
                    "ok": False,
                    "source": None,
                    "nPoints": 0,
                    "error": "parse returned empty",
                }
            else:
                parseResults[port] = {
                    "ok": True,
                    "source": trace.source,
                    "nPoints": int(len(trace.values)),
                }
        except Exception as exc:  # noqa: BLE001
            parseResults[port] = {
                "ok": False,
                "source": None,
                "nPoints": 0,
                "error": str(exc),
            }

    seriesCount = 0
    if not settings.useDemo:
        try:
            loaded = loadProcessedSeries(shotNo, kind, startMs, endMs)
            seriesCount = len(loaded) if loaded else 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("diagnose loadProcessedSeries failed: %s", exc)
            seriesCount = 0

    wouldUseDemo = bool(settings.useDemo and seriesCount == 0)
    shotDirOk = (
        ftpClient.shotDirExists(shotNo) if ftpClient.isFtpConfigured() else None
    )
    if ftpClient.isFtpConfigured():
        probe = ftpClient.probeFtpConnection()
    else:
        probe = {"ok": False, "error": "FTP host/user not configured"}

    return {
        "shotNo": shotNo,
        "kind": kind,
        "useDemo": settings.useDemo,
        "ftp": ftpClient.ftpConfigStatus(),
        "ftpProbe": probe,
        "shotDirExists": shotDirOk,
        "ports": ports,
        "fetchResults": fetchResults,
        "parseResults": parseResults,
        "seriesCount": seriesCount,
        "wouldUseDemo": wouldUseDemo,
        "startMs": startMs,
        "endMs": endMs,
        "fallbackNote": buildMissingDataNote(shotNo, kind) if seriesCount == 0 else None,
    }


def summarizeKind(kind: WaveformKind) -> dict[str, object]:
    """診断種別の設定サマリ（デバッグ／UI 用）。"""
    meta = resolveKindMeta(kind)
    channels = channelNamesFor(kind)
    portMap = {ch: resolvePorts(kind, ch, None) for ch in channels}
    return {
        "kind": kind,
        "label": meta["label"],
        "unit": meta["unit"],
        "channels": channels,
        "ports": portMap,
        "ftpBasePath": str(getSettings().ftpBasePath),
        "ftpDir": ftpDirFor(kind),
    }
