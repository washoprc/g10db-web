"""ローカル波形ファイル経由の結合テスト。"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

os.environ["USE_DEMO"] = "0"
os.environ["CONFIG_ROOT"] = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config")
)


@pytest.fixture()
def dataRoot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """一時 DATA_ROOT を Settings に注入する。"""
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("USE_DEMO", "0")
    from app.config import getSettings

    getSettings.cache_clear()
    yield tmp_path
    getSettings.cache_clear()


def testLoadLocalHaWaveform(dataRoot: Path) -> None:
    """DATA_ROOT の Ha バイナリを読み後処理する。"""
    shotNo = 123456
    channel = "Ha_CC"
    shotDir = dataRoot / str(shotNo) / "Ha"
    shotDir.mkdir(parents=True)
    nPoints = 50
    header = struct.pack("<iff", nPoints, 1.0, 0.0)
    values = struct.pack("<" + "f" * nPoints, *[float(i) * 0.1 for i in range(nPoints)])
    (shotDir / f"{channel}.dat").write_bytes(header + values)

    from app.services.waveformService import getWaveform

    response = getWaveform(shotNo, "Ha", startMs=0, endMs=200)
    assert response.demoMode is False
    assert any(s.name == channel for s in response.series)
    assert len(response.series[0].points) > 0
