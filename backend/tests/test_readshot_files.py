"""ローカル波形ファイル経由の結合テスト。"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

os.environ["USE_DEMO"] = "0"


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
    """ftp_cache 上の CAMAC ポートを HaGraph 式で読む。"""
    shotNo = 123456
    port = "CTHA01"
    shotDir = dataRoot / "ftp_cache" / str(shotNo)
    shotDir.mkdir(parents=True)
    # 160B ヘッダ + BE uint16 サンプル（legacy-camac）
    header = struct.pack(">" + "H" * 80, *([0] * 80))
    # HaCT の offset 窓は trig 後 ~1010 点付近のため十分な長さを確保
    nSamples = 8000
    samples = struct.pack(">" + "H" * nSamples, *([2100] * nSamples))
    (shotDir / port).write_bytes(header + samples)

    from app.services.waveformService import getWaveform

    response = getWaveform(shotNo, "Ha", startMs=0, endMs=200)
    assert response.demoMode is False
    assert len(response.series) >= 1
    assert any("HaCT" in s.name or port in s.name for s in response.series)
    assert len(response.series[0].points) > 0
