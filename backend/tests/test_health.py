from fastapi.testclient import TestClient

from app.main import app


def test_read_state():
    client = TestClient(app)
    resp = client.get("/system/state")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tunnel_level_m"] > 0
    assert payload["tunnel_level_l2_m"] > 0
