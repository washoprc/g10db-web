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
from app.models.schemas import (
    WaveformKind,
    WaveformPoint,
    WaveformResponse,
    WaveformSeries,
)
from app.services import ftpClient
from app.services.configLoader import loadGroupList, loadTableList
from app.services.portResolver import resolvePorts
from app.services.processors import loadHaDetectorMeta, processTrace
from app.services.readshot import parseReadshot

logger = logging.getLogger(__name__)


def buildFallbackNote(
    shotNo: int,
    kind: WaveformKind,
    detail: str | None = None,
) -> str:
    """デモフォールバック時の具体的な注意文を組み立てる。"""
    settings = getSettings()
    reasons: list[str] = []
    if settings.useDemo:
        reasons.append("USE_DEMO=1")
    if not settings.ftpHost:
        reasons.append("FTP_HOST is empty")
    if not settings.ftpUser:
        reasons.append("FTP_USER is empty")
    if not settings.ftpPassword:
        reasons.append("FTP_PASSWORD is empty")
    reasonText = ", ".join(reasons) if reasons else "FTP fetch/parse returned no series"
    parts = [
        f"Shot {shotNo} {kind}: demo waveform ({reasonText}).",
        f"Host={settings.ftpHost or '(none)'} base={settings.ftpBasePath}.",
    ]
    if detail:
        parts.append(detail)
    parts.append(
        "Set USE_DEMO=0 and FTP_PASSWORD in .env, then "
        "docker compose up -d --build --force-recreate api."
    )
    return " ".join(parts)


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


def loadProcessedSeries(
    shotNo: int,
    kind: WaveformKind,
    startMs: float,
    endMs: float,
) -> list[WaveformSeries] | None:
    """ローカル／FTP からポートを読み、後処理して返す。"""
    meta = resolveKindMeta(kind)
    names = channelNamesFor(kind)
    series: list[WaveformSeries] = []

    # 必要ポートを集約して FTP 一括取得
    neededPorts: list[str] = []
    for name in names:
        for port in resolvePorts(kind, name, shotNo):
            if port not in neededPorts and findLocalPortFile(shotNo, port) is None:
                neededPorts.append(port)

    if neededPorts and ftpClient.isFtpConfigured() and not getSettings().useDemo:
        ftpClient.fetchPortFiles(shotNo, neededPorts)

    seenVcc = False
    for name in names:
        ports = resolvePorts(kind, name, shotNo)
        haMeta = loadHaDetectorMeta(name, shotNo) if kind == "Ha" else None
        defaultDt = haMeta.sampMs if haMeta is not None else 1.0

        loadedFromPorts = False
        if ports:
            # VCC は同一ポートを多重表示しない
            if kind == "VCC":
                if seenVcc:
                    continue
                seenVcc = True

            for channelIndex, port in enumerate(ports):
                path = findLocalPortFile(shotNo, port)
                if path is None and ftpClient.isFtpConfigured() and not getSettings().useDemo:
                    path = ftpClient.fetchPortFile(shotNo, port)
                if path is None:
                    continue
                trace = parseReadshot(
                    path,
                    startMs=startMs if kind != "Ha" or haMeta is None else -1e9,
                    endMs=endMs if kind != "Ha" or haMeta is None else 1e9,
                    defaultDtMs=defaultDt,
                )
                if trace is None or len(trace.values) == 0:
                    continue
                # Ha CAMAC は applyHaCamac 内で時間軸を trig/samp で再構築するため
                # パース時は全点読み、後で窓切りする
                processed = processTrace(
                    kind,
                    name,
                    trace,
                    shotNo=shotNo,
                    channelIndex=channelIndex,
                    haMeta=haMeta,
                )
                if kind == "Ha" and haMeta is not None:
                    mask = (processed.timesMs >= startMs) & (processed.timesMs <= endMs)
                    from app.services.readshot import ShotTrace

                    processed = ShotTrace(
                        timesMs=processed.timesMs[mask],
                        values=processed.values[mask],
                        source=processed.source,
                    )
                seriesName = port if kind == "VCC" else (
                    f"{name}:{port}" if len(ports) > 1 else name
                )
                item = _seriesFromTrace(seriesName, meta["unit"], processed)
                if item:
                    series.append(item)
                    loadedFromPorts = True

        if loadedFromPorts:
            continue

        # ポート未取得時は旧レイアウトのローカルファイルを試す
        files = findLocalChannelFiles(shotNo, kind, name)
        if not files:
            continue
        trace = parseReadshot(files[0], startMs=startMs, endMs=endMs)
        if trace is None or len(trace.values) == 0:
            continue
        processed = processTrace(kind, name, trace, shotNo=shotNo)
        item = _seriesFromTrace(name, meta["unit"], processed)
        if item:
            series.append(item)

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

    return WaveformResponse(
        shotNo=shotNo,
        kind=kind,
        startMs=startMs,
        endMs=endMs,
        series=demoSeries(kind, startMs, endMs),
        demoMode=True,
        note=buildFallbackNote(shotNo, kind),
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
    startMs: float = 0.0,
    endMs: float = 200.0,
) -> dict[str, object]:
    """ショット波形の取得・パース診断（デモバッジ原因調査用）。"""
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

    wouldUseDemo = bool(settings.useDemo or seriesCount == 0)
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
        "ports": ports,
        "fetchResults": fetchResults,
        "parseResults": parseResults,
        "seriesCount": seriesCount,
        "wouldUseDemo": wouldUseDemo,
        "fallbackNote": buildFallbackNote(shotNo, kind) if wouldUseDemo else None,
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
