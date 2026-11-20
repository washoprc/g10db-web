"""API の基本動作テスト（デモモード）。"""

import os

os.environ["USE_DEMO"] = "1"
os.environ["CONFIG_ROOT"] = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config")
)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def testHealth() -> None:
    """ヘルスチェックが ok を返す。"""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["demoMode"] is True


def testLatestShots() -> None:
    """最新ショット検索。"""
    response = client.get("/api/shots/latest?limit=3")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "latest"
    assert body["count"] == 3
    assert body["items"][0]["shotNo"] is not None


def testByNumberAndDate() -> None:
    """番号・日付検索。"""
    byNumber = client.get("/api/shots/by-number?start=100&limit=2")
    assert byNumber.status_code == 200
    assert byNumber.json()["count"] == 2

    byDate = client.get("/api/shots/by-date?date=2026-11-20&limit=2")
    assert byDate.status_code == 200
    assert byDate.json()["count"] == 2


def testWaveform() -> None:
    """波形 API。"""
    response = client.get("/api/waveforms/120000/Ha?startMs=0&endMs=100")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "Ha"
    assert len(body["series"]) >= 1
    assert len(body["series"][0]["points"]) > 10


def testConfigMeta() -> None:
    """設定メタ。"""
    response = client.get("/api/waveforms/meta/config")
    assert response.status_code == 200
    body = response.json()
    assert "groups" in body
    assert "tables" in body
