from fastapi.testclient import TestClient

from app.main import app


def test_status_and_config_endpoints():
    client = TestClient(app)
    status = client.get("/status")
    config = client.get("/config")
    assert status.status_code == 200
    assert config.status_code == 200
    assert config.json()["trading"]["mode"] == "paper"


def test_pnl_endpoint_shape():
    client = TestClient(app)
    response = client.get("/pnl")
    assert response.status_code == 200
    body = response.json()
    assert "net_pnl" in body
    assert "equity_curve" in body
