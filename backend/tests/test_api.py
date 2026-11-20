"""API の基本動作テスト（デモモード）。"""

import os
import struct
from pathlib import Path

os.environ["USE_DEMO"] = "1"
os.environ["CONFIG_ROOT"] = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config")
)

from fastapi.testclient import TestClient

from app.main import app
from app.services.readshot import parseReadshot
from app.services.processors import applyHa, applyNl
from app.services.readshot import ShotTrace
import numpy as np

client = TestClient(app)


def testHealth() -> None:
    """ヘルスチェックが ok を返す。"""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["demoMode"] is True


def testLatestShots() -> None:
    """最新ショット検索（クラシック ShowTable パネル付き）。"""
    response = client.get("/api/shots/latest?limit=3")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "latest"
    assert body["count"] == 3
    assert body["items"][0]["shotNo"] is not None
    assert len(body["groupNames"]) == 25
    assert body["groupNames"][0] == "Main"
    assert body["groupNames"][1] == "Coil"
    assert body["groupNames"][-1] == "Comment"
    assert len(body["panels"]) == 3
    assert len(body["panels"][0]) == 25

    mainCells = body["panels"][0][0]["cells"]
    shotLinks = [c for c in mainCells if c.get("isShotLink")]
    assert shotLinks, "Main 列にショット番号リンクが必要"
    assert shotLinks[0]["shotNo"] == body["items"][0]["shotNo"]

    coilCells = body["panels"][0][1]["cells"]
    coilTexts = [c["text"] for c in coilCells]
    assert any(text.startswith("CR ") for text in coilTexts), coilTexts


def testByNumberAndDate() -> None:
    """番号・日付検索。"""
    byNumber = client.get("/api/shots/by-number?start=100&limit=2")
    assert byNumber.status_code == 200
    assert byNumber.json()["count"] == 2

    byDate = client.get("/api/shots/by-date?date=2026-11-20&limit=2")
    assert byDate.status_code == 200
    assert byDate.json()["count"] == 2

    byYymmdd = client.get("/api/shots/by-date?date=261120&limit=1")
    assert byYymmdd.status_code == 200


def testLimitCappedAt30() -> None:
    """limit は最大 30。"""
    response = client.get("/api/shots/latest?limit=30")
    assert response.status_code == 200
    assert response.json()["count"] == 30

    over = client.get("/api/shots/latest?limit=99")
    assert over.status_code == 422


def testWaveform() -> None:
    """波形 API。"""
    for kind in ("Ha", "DM", "NL", "VCC"):
        response = client.get(f"/api/waveforms/120000/{kind}?startMs=0&endMs=100")
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == kind
        assert len(body["series"]) >= 1
        assert len(body["series"][0]["points"]) > 10


def testConfigMeta() -> None:
    """設定メタ。"""
    response = client.get("/api/waveforms/meta/config")
    assert response.status_code == 200
    body = response.json()
    assert "groups" in body
    assert "tables" in body
    assert any(g.get("id") == "Ha" for g in body["groups"])
    assert "haCoefFiles" in body
    assert "nlFiles" in body


def testNoArbitrarySqlRoute() -> None:
    """任意 SQL エンドポイントが無いこと。"""
    for path in ("/api/arb", "/api/sql", "/api/query"):
        assert client.get(path).status_code == 404


def testReadshotHeaderBinary(tmp_path: Path) -> None:
    """readshot ヘッダ付きバイナリ。"""
    nPoints = 10
    dtMs = 2.0
    t0Ms = 0.0
    header = struct.pack("<iff", nPoints, dtMs, t0Ms)
    values = struct.pack("<" + "f" * nPoints, *range(nPoints))
    path = tmp_path / "ch.dat"
    path.write_bytes(header + values)
    trace = parseReadshot(path, startMs=0, endMs=100)
    assert trace is not None
    assert len(trace.values) == nPoints


def testProcessors() -> None:
    """Ha / NL 校正が適用される。"""
    times = np.arange(5, dtype=np.float64)
    values = np.ones(5, dtype=np.float64)
    trace = ShotTrace(timesMs=times, values=values, source="test")
    ha = applyHa(trace, "Ha_CC")
    assert ha.values.shape == values.shape
    nl = applyNl(trace, "NL_CC")
    assert float(nl.values[0]) != 0.0
