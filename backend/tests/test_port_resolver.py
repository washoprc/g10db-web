"""ポート名解決と CAMAC パーサの単体テスト。"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import numpy as np
import pytest

os.environ["USE_DEMO"] = "1"
os.environ["CONFIG_ROOT"] = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config")
)


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
    """DM / VCC の固定ポート名。"""
    from app.services.portResolver import resolveDmPort, resolvePorts, resolveVccPort

    assert resolveDmPort("DM_CC") == "DMC500"
    assert resolveDmPort("DM_A") == "DMC600"
    assert resolveDmPort("DM_Barrier") is None
    assert resolveVccPort() == "VCCC00"
    assert resolvePorts("DM", "DM_CC") == ["DMC500"]
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
    """HaGraph 式 Intensity=Data*coef*const/(amp*glass)-BG。"""
    from app.services.processors import HaDetectorMeta, applyHaCamac
    from app.services.readshot import ShotTrace

    meta = HaDetectorMeta(
        detector="HaCT",
        ports=["CTHA01"],
        coefs=[2.0],
        consts=[1.0],
        amps=[2.0],
        glassTrans=[1.0],
        offset=10.0,
        bit=12,
        sampMs=0.2,
        trigMs=50.0,
        chNumber=1,
    )
    raw = ShotTrace(
        timesMs=np.arange(5, dtype=np.float64),
        values=np.asarray([20.0, 30.0, 40.0, 50.0, 60.0]),
        source="legacy-camac:CTHA01",
    )
    # scale = 2*1/(2*1) = 1 → values - 10
    out = applyHaCamac(raw, meta, channelIndex=0)
    assert float(out.values[0]) == pytest.approx(10.0)
    assert float(out.timesMs[0]) == pytest.approx(50.0)
    assert float(out.timesMs[1]) == pytest.approx(50.2)


def testFtpRemotePathHasNoExtension() -> None:
    """リモートパスに .dat や診断サブディレクトリが無い。"""
    from app.services.ftpClient import remotePortPath

    path = remotePortPath(200000, "CTHA01")
    assert path.endswith("/200000/CTHA01")
    assert ".dat" not in path
    assert "/Ha/" not in path
