"""ポート名解決と CAMAC / 後処理の単体テスト。"""

from __future__ import annotations

import math
import os
import struct
from pathlib import Path

import numpy as np
import pytest

os.environ["USE_DEMO"] = "1"


def _resolveConfigRoot() -> str:
    """ホスト / コンテナ双方で有効な config ルートを返す。"""
    candidates = [
        os.environ.get("CONFIG_ROOT"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config")),
        "/app/config",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return candidate
    return candidates[1] or "/app/config"


os.environ["CONFIG_ROOT"] = _resolveConfigRoot()


@pytest.fixture(autouse=True)
def clearSettingsCache() -> None:
    """各テスト前後で Settings キャッシュをクリアする。"""
    from app.config import getSettings

    getSettings.cache_clear()
    yield
    getSettings.cache_clear()


def testResolveHaPortsFromCoef() -> None:
    """HaCT の port.txt をショット適合で読む。"""
    from app.services.portResolver import resolveHaPorts, resolvePorts

    ports = resolveHaPorts("HaCT", 200000)
    assert ports == ["CTHA01", "CTHA02", "CTHA03", "CTHA04", "CTHA05"]
    assert resolvePorts("Ha", "HaCT", 200000) == ports


def testResolveNlPortsFromConfig() -> None:
    """NLCCNEW.txt の channelA/B をポートにする。"""
    from app.services.portResolver import resolveNlPorts, resolvePorts

    ports = resolveNlPorts("NLCCNEW")
    assert ports == ["NLCC11", "NLCC10"]
    assert resolvePorts("NL", "NLCCNEW", None) == ports


def testResolveDmAndVccFixedPorts() -> None:
    """DM はペア、VCC は固定ポート。"""
    from app.services.portResolver import resolveDmPorts, resolvePorts, resolveVccPort

    assert resolveDmPorts("DM_CC") == ["DMC500", "DMC600"]
    assert resolveDmPorts("DM_Barrier") == []
    assert resolveVccPort() == "VCCC00"
    assert resolvePorts("DM", "DM_CC") == ["DMC500", "DMC600"]
    assert resolvePorts("VCC", "VCC1") == ["VCCC00"]


def testParseLegacyCamacUint16(tmp_path: Path) -> None:
    """160 バイトヘッダ + BE uint16 サンプルを読む。"""
    from app.services.readshot import parseReadshot

    header = struct.pack(">" + "H" * 80, *([0] * 80))
    samples = struct.pack(">" + "H" * 10, *range(100, 110))
    path = tmp_path / "test_camac_u16.bin"
    path.write_bytes(header + samples)

    trace = parseReadshot(path, startMs=0, endMs=100, defaultDtMs=1.0)
    assert trace is not None
    assert trace.source.startswith("legacy-camac")
    assert len(trace.values) == 10
    assert float(trace.values[0]) == 100.0
    assert float(trace.values[-1]) == 109.0


def testApplyHaCamacFormula() -> None:
    """HaGraph 式 (data-max-bg)/max*5000*coef。"""
    from app.services.processors import HaDetectorMeta, applyHaCamac
    from app.services.readshot import ShotTrace

    meta = HaDetectorMeta(
        detector="HaCT",
        ports=["CTHA01"],
        channelCoefs=[2.0],
        offset1Ms=50.0,
        offset2Samples=2,
        bit=12,
        sampMs=0.2,
        trigMs=50.0,
        chNumber=1,
    )
    # max=2048。先頭2点で baseline=mean(2,4)=3
    raw = ShotTrace(
        timesMs=np.arange(5, dtype=np.float64),
        values=np.asarray([2050.0, 2052.0, 2060.0, 2070.0, 2080.0]),
        source="legacy-camac:CTHA01",
    )
    out = applyHaCamac(raw, meta, channelIndex=0)
    # (2060-2048-3)/2048*5000*2
    expected = (2060.0 - 2048.0 - 3.0) / 2048.0 * 5000.0 * 2.0
    assert float(out.values[2]) == pytest.approx(expected)
    assert float(out.timesMs[0]) == pytest.approx(50.0)
    assert float(out.timesMs[1]) == pytest.approx(50.2)


def testLoadCamacSamplesReadsToEof(tmp_path: Path) -> None:
    """ヘッダ 160 バイトを除き、ファイル末尾まで読む。"""
    from app.services.readshot import loadCamacSamples

    nSamples = 5000
    header = struct.pack(">" + "H" * 80, *([7] * 80))
    samples = struct.pack(">" + "H" * nSamples, *range(nSamples))
    path = tmp_path / "DMC500"
    path.write_bytes(header + samples)

    trace = loadCamacSamples(path, defaultDtMs=0.1)
    assert trace is not None
    assert len(trace.values) == nSamples
    assert float(trace.values[0]) == 0.0
    assert float(trace.values[-1]) == float(nSamples - 1)
    assert float(trace.timesMs[-1]) == pytest.approx((nSamples - 1) * 0.1)


def testResolveTimeWindowByPulseMode(monkeypatch: pytest.MonkeyPatch) -> None:
    """表示窓はロングパルス 50–450、それ以外 50–250。"""
    from app.services import waveformService

    class Settings:
        """DB 照会を有効にする最小設定。"""

        useDemo = False

    def fakeFetchAll(sql: str, params: tuple[int, ...]) -> list[dict[str, float]]:
        shotNo = params[0]
        if shotNo == 1:
            return [{"time_e": 800.0}]
        if shotNo == 2:
            return [{"time_e": 300.0}]
        if shotNo == 3:
            return [{"time_e": 120.0}]
        return []

    monkeypatch.setattr(waveformService, "getSettings", lambda: Settings())
    monkeypatch.setattr(waveformService, "fetchAll", fakeFetchAll)

    assert waveformService.resolveTimeWindow(1) == (50.0, 450.0)
    assert waveformService.resolveTimeWindow(2) == (50.0, 250.0)
    assert waveformService.resolveTimeWindow(3) == (50.0, 250.0)
    assert waveformService.resolveTimeWindow(4) == (50.0, 250.0)


def testApplyDmPairProducesSeries() -> None:
    """DM ペア処理はヘッダ除去後の全点を使う。"""
    from app.services.processors import applyDmPair
    from app.services.readshot import ShotTrace

    n = 5120
    maxAdc = 2048.0
    t1 = ShotTrace(
        timesMs=np.arange(n, dtype=np.float64) * 0.1,
        values=np.full(n, maxAdc + 10.0),
        source="legacy-camac:DMC500",
    )
    t2 = ShotTrace(
        timesMs=np.arange(n, dtype=np.float64) * 0.1,
        values=np.full(n, maxAdc + 20.0),
        source="legacy-camac:DMC600",
    )
    out = applyDmPair(t1, t2)
    assert len(out.values) == n
    assert np.isfinite(out.values).all()


def testApplyNlPairAtan2() -> None:
    """NL 位相アンラップがバイアス除去後の系列を返す。"""
    from app.services.processors import applyNlPair
    from app.services.readshot import ShotTrace

    n = 200
    maxAdc = 2048.0
    angles = np.linspace(0, math.pi, n)
    t1 = ShotTrace(
        timesMs=np.arange(n, dtype=np.float64),
        values=maxAdc + 100.0 * np.sin(angles),
        source="legacy-camac:NLCC11",
    )
    t2 = ShotTrace(
        timesMs=np.arange(n, dtype=np.float64),
        values=maxAdc + 100.0 * np.cos(angles),
        source="legacy-camac:NLCC10",
    )
    out = applyNlPair(t1, t2, sampMs=0.02, trigMs=50.0, bit=12)
    assert len(out.values) == n
    assert float(out.values[0]) == pytest.approx(0.0, abs=1e-9)
    assert float(out.timesMs[0]) == pytest.approx(50.0)


def testApplyVccScale() -> None:
    """VCC bipolar × camac_range/unit（PHP は camac_range=2e-5）。"""
    from app.services.processors import VCC_CAMAC_RANGE, VCC_UNIT, applyVcc
    from app.services.readshot import ShotTrace

    assert VCC_CAMAC_RANGE == pytest.approx(2.0e-5)
    maxAdc = 2048.0
    raw = ShotTrace(
        timesMs=np.asarray([0.0, 1.0]),
        values=np.asarray([maxAdc + maxAdc, maxAdc]),
        source="legacy-camac:VCCC00",
    )
    out = applyVcc(raw, "VCC1")
    expected = (maxAdc / maxAdc) * (VCC_CAMAC_RANGE / VCC_UNIT)
    assert float(out.values[0]) == pytest.approx(expected)
    assert float(out.values[0]) == pytest.approx(20.0)
    assert float(out.values[1]) == pytest.approx(0.0)


def testFtpRemotePathHasNoExtension() -> None:
    """リモートパスに .dat や診断サブディレクトリが無い。"""
    from app.services.ftpClient import remotePortPath

    path = remotePortPath(200000, "CTHA01")
    assert path.endswith("/200000/CTHA01")
    assert ".dat" not in path
    assert "/Ha/" not in path


def testFtpExceptAllErrorsIsValid() -> None:
    """ftplib.all_errors を直接 except できること。"""
    import ftplib

    try:
        raise ConnectionRefusedError("refused")
    except ftplib.all_errors as exc:
        assert "refused" in str(exc)
