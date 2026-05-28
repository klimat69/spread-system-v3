from fastapi.testclient import TestClient

from app.main import app


def test_status_and_config_endpoints():
    client = TestClient(app)
    status = client.get("/status")
    config = client.get("/config")
    assert status.status_code == 200
    assert config.status_code == 200
    body = config.json()
    assert body["exchange"]["name"] == "mexc"
    assert body["trading"]["mode"] == "paper"


def test_symbols_endpoint_with_legacy_sandbox_flag(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        '{"exchange":{"name":"mexc","sandbox":true},"trading":{"mode":"paper","market_type":"spot","symbol":"BTC/USDT","order_size":0.001,"cycle_interval_seconds":1}}',
        encoding="utf-8",
    )
    from app.config import ConfigService

    service = ConfigService(path)
    loaded = service.load(force=True)
    assert loaded.exchange.sandbox is False

    async def fake_catalog(_config, market_type):
        return {"quotes": ["USDT"], "symbols_by_quote": {"USDT": ["BTC/USDT"]}}

    async def fake_symbols(_config, market_type, quote=None):
        return ["BTC/USDT"]

    monkeypatch.setattr("app.main.config_service", service)
    monkeypatch.setattr("app.main.exchange_adapter.fetch_symbol_catalog", fake_catalog)
    monkeypatch.setattr("app.main.exchange_adapter.fetch_symbols", fake_symbols)

    client = TestClient(app)
    response = client.get("/symbols?market_type=spot")
    assert response.status_code == 200


def test_symbols_endpoint_returns_mexc_catalog(monkeypatch):
    async def fake_catalog(_config, market_type):
        return {
            "quotes": ["USDT", "USDC"],
            "symbols_by_quote": {"USDT": ["BTC/USDT"], "USDC": ["BTC/USDC"]},
        }

    async def fake_symbols(_config, market_type, quote=None):
        if quote == "USDC":
            return ["BTC/USDC"]
        return ["BTC/USDT"]

    monkeypatch.setattr("app.main.exchange_adapter.fetch_symbol_catalog", fake_catalog)
    monkeypatch.setattr("app.main.exchange_adapter.fetch_symbols", fake_symbols)

    client = TestClient(app)
    response = client.get("/symbols?market_type=spot&quote=USDC")
    assert response.status_code == 200
    body = response.json()
    assert body["exchange"] == "mexc"
    assert body["quote"] == "USDC"
    assert "BTC/USDC" in body["symbols"]


def test_pnl_endpoint_shape():
    client = TestClient(app)
    response = client.get("/pnl")
    assert response.status_code == 200
    body = response.json()
    assert "net_pnl" in body
    assert "equity_curve" in body


def test_market_state_endpoint_returns_health_contract():
    client = TestClient(app)
    response = client.get("/market/state")
    assert response.status_code == 200
    body = response.json()
    assert "health" in body
    assert "feed_state" in body
    assert "ws_status" in body
