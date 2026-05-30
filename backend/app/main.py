from __future__ import annotations

import logging
import asyncio
import time
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from pydantic import BaseModel

from .config import AppConfig, config_service
from .credentials import credential_store
from .database import trade_repository
from .engine import trading_engine
from .exchange import exchange_adapter
from .market_data import market_data_engine
from .websocket import manager
from .validate_exchange import validate as validate_exchange

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Spread System v3 API", version="3.0.0")
# Desktop Electron loads the UI from file:// (Origin: null). Dev uses Vite on :5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "app://spread-system-v3",
        "null",
    ],
    allow_origin_regex=r"^app://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CredentialPayload(BaseModel):
    exchange: str
    api_key: str
    api_secret: str
    password: str = ""


class ConnectivityTestPayload(BaseModel):
    exchange: str
    symbol: str
    market_type: str


def pnl_payload() -> dict:
    summary = trade_repository.pnl_summary()
    return {**summary, "total_pnl": summary["net_pnl"], "daily_pnl": trade_repository.daily_pnl()}


@app.on_event("startup")
async def startup() -> None:
    config_service.ensure_exists()
    trade_repository.init_db()
    trade_repository.insert_event("info", "Backend API started")


@app.on_event("shutdown")
async def shutdown() -> None:
    if trading_engine.running:
        await trading_engine.stop()
    trade_repository.insert_event("info", "Backend API stopped")


@app.get("/status")
async def get_status() -> dict:
    return trading_engine.status()


@app.get("/trades")
async def get_trades(
    symbol: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[dict]:
    return trade_repository.list_trades(symbol=symbol, start=start, end=end, limit=limit)


@app.get("/orders")
async def get_orders(symbol: str | None = None, limit: Annotated[int, Query(ge=1, le=5000)] = 500) -> list[dict]:
    return trade_repository.list_orders(symbol=symbol, limit=limit)


@app.get("/fills")
async def get_fills(symbol: str | None = None, limit: Annotated[int, Query(ge=1, le=5000)] = 500) -> list[dict]:
    return trade_repository.list_fills(symbol=symbol, limit=limit)


@app.get("/positions")
async def get_positions(symbol: str | None = None) -> list[dict]:
    return trade_repository.list_positions(symbol=symbol)


@app.get("/reconciliation")
async def get_reconciliation() -> dict:
    return {
        **trade_repository.reconciliation_status(),
        "events": trade_repository.list_reconciliation_events(limit=100),
    }


@app.get("/market-data/health")
async def get_market_data_health() -> dict:
    config = config_service.load(force=True)
    await market_data_engine.ensure_started(config)
    return await market_data_engine.health(config, persist=False)


@app.get("/market/state")
async def get_market_state() -> dict:
    config = config_service.load(force=True)
    return await market_data_engine.market_state(config)


@app.get("/live-eligibility")
async def get_live_eligibility() -> dict:
    config = config_service.load(force=True)

    market_data = trade_repository.latest_market_data_health(config.exchange.name, config.trading.market_type, config.trading.symbol)
    validation = trade_repository.latest_validation_result(config.exchange.name, config.trading.market_type, config.trading.symbol)
    reconciliation = trade_repository.reconciliation_status()

    reasons: list[str] = []
    if market_data.get("status") != "OK":
        reasons.append(f"market_data_unhealthy:{market_data.get('reason')}")
    if validation.get("status") != "PASSED":
        reasons.append(f"validation_failed:{validation.get('status')}")
    if reconciliation.get("blocking"):
        reasons.append("reconciliation_blocked")

    eligible = (market_data.get("status") == "OK" and validation.get("status") == "PASSED" and not reconciliation.get("blocking"))

    return {
        "eligible": bool(eligible),
        "reasons": reasons,
        "market_data": market_data,
        "validation": validation,
        "reconciliation": reconciliation,
    }


@app.get("/latency")
async def get_latency(limit: Annotated[int, Query(ge=1, le=5000)] = 200) -> list[dict]:
    config = config_service.load(force=True)
    return trade_repository.list_latency_metrics(config.exchange.name, config.trading.market_type, config.trading.symbol, limit=limit)


@app.get("/pnl")
async def get_pnl() -> dict:
    return pnl_payload()


@app.get("/config")
async def get_config() -> dict:
    return config_service.load(force=True).model_dump()


@app.get("/symbols")
async def get_symbols(
    market_type: str = Query(default="swap", pattern="^(spot|swap)$"),
    quote: str | None = None,
) -> dict:
    config = config_service.load(force=True)
    try:
        catalog = await exchange_adapter.fetch_symbol_catalog(config, market_type)
    except Exception as exc:
        logger.exception("Failed to load MEXC symbol catalog")
        raise HTTPException(
            status_code=503,
            detail=f"Could not load symbols from MEXC: {exc}",
        ) from exc
    symbols_by_quote = catalog.get("symbols_by_quote")
    quotes = catalog.get("quotes")
    if not isinstance(symbols_by_quote, dict) or not isinstance(quotes, list):
        raise HTTPException(status_code=503, detail="MEXC symbols response format is invalid")
    selected_quote = quote.upper() if quote else (quotes[0] if quotes else None)
    symbols = (
        list(symbols_by_quote.get(selected_quote, []))
        if selected_quote
        else await exchange_adapter.fetch_symbols(config, market_type)
    )
    symbols_meta = catalog.get("symbols_meta")
    popular_by_quote = catalog.get("popular_by_quote")
    if not isinstance(symbols_meta, dict):
        symbols_meta = {}
    quote_popular: list[str] = []
    if isinstance(popular_by_quote, dict) and selected_quote:
        raw_popular = popular_by_quote.get(selected_quote, [])
        if isinstance(raw_popular, list):
            quote_popular = [s for s in raw_popular if s in symbols]
    from .mexc_symbols import GOLD_FUTURES_CCXT_CANDIDATES, resolve_mexc_trading_symbol

    usdt_swap = symbols_by_quote.get("USDT", []) if isinstance(symbols_by_quote.get("USDT"), list) else []
    gold_futures_symbol: str | None = None
    if market_type == "swap":
        for candidate in GOLD_FUTURES_CCXT_CANDIDATES:
            hit = next((s for s in usdt_swap if s.upper() == candidate.upper()), None)
            if hit:
                gold_futures_symbol = hit
                break
        if gold_futures_symbol is None:
            gold_futures_symbol = resolve_mexc_trading_symbol("XAUT/USDT", "swap")
    return {
        "exchange": "mexc",
        "market_type": market_type,
        "quotes": quotes,
        "quote": selected_quote,
        "symbols_by_quote": symbols_by_quote,
        "symbols": symbols,
        "popular_symbols": quote_popular,
        "symbols_meta": symbols_meta,
        "gold_futures_symbol": gold_futures_symbol,
    }


@app.post("/config")
async def save_config(config: AppConfig) -> dict:
    from .mexc_symbols import resolve_mexc_trading_symbol

    try:
        available: list[str] = []
        try:
            catalog = await exchange_adapter.fetch_symbol_catalog(config, config.trading.market_type)
            by_quote = catalog.get("symbols_by_quote")
            if isinstance(by_quote, dict):
                for items in by_quote.values():
                    if isinstance(items, list):
                        available.extend(items)
        except Exception:
            logger.debug("Symbol catalog unavailable during config save", exc_info=True)
        resolved = resolve_mexc_trading_symbol(
            config.trading.symbol,
            config.trading.market_type,
            available=available or None,
        )
        if resolved != config.trading.symbol:
            config = config.model_copy(
                update={"trading": config.trading.model_copy(update={"symbol": resolved})}
            )
        saved = config_service.save(config)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if trading_engine.running:
        await market_data_engine.ensure_started(saved)
    trade_repository.insert_event("info", "Config saved and applied")
    await manager.broadcast({"type": "config", "config": saved.model_dump()})
    return saved.model_dump()


@app.post("/start")
async def start_engine() -> dict:
    return await trading_engine.start()


@app.post("/stop")
async def stop_engine() -> dict:
    return await trading_engine.stop()


@app.post("/sync")
async def sync_exchange() -> dict:
    config = config_service.load(force=True)
    if config.trading.mode != "live":
        return {"status": "BLOCKED", "reason": "exchange sync requires live mode and credentials"}
    return await trading_engine.reconciliation.sync(config)


@app.post("/credentials")
async def set_exchange_credentials(payload: CredentialPayload) -> dict:
    credential_store.set(payload.exchange, payload.api_key, payload.api_secret, payload.password)
    trade_repository.insert_event("info", f"Exchange credentials injected for {payload.exchange}")
    return {"status": "OK"}


@app.post("/connectivity-test")
async def connectivity_test(payload: ConnectivityTestPayload) -> dict:
    # Connectivity test used by the first-launch wizard.
    # It verifies: (1) websocket DOM/tape health, (2) exchange validation against the local ledger.
    config = config_service.load(force=True).model_copy(deep=True)
    config.exchange.name = payload.exchange  # type: ignore[assignment]
    config.trading.symbol = payload.symbol.upper()
    config.trading.market_type = payload.market_type  # type: ignore[assignment]

    await market_data_engine.ensure_started(config)

    # Wait briefly for websocket DOM+tape to synchronize.
    timeout_s = 15.0
    started_at = time.monotonic()
    last_health: dict | None = None
    last_snapshot = None
    while time.monotonic() - started_at < timeout_s:
        last_snapshot, last_health = await market_data_engine.snapshot(config)
        if last_health and last_health.get("status") == "OK" and last_snapshot is not None:
            break
        await asyncio.sleep(0.5)

    validation = await validate_exchange(payload.symbol, payload.market_type, payload.exchange)
    ok = (last_health or {}).get("status") == "OK" and validation.get("status") == "PASSED"
    return {
        "status": "PASSED" if ok else "FAILED",
        "market_data": last_health,
        "validation": validation,
    }


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int) -> dict:
    config = config_service.load(force=True)
    if config.trading.mode != "live" or not config.trading.live_trading_enabled:
        raise HTTPException(status_code=409, detail="real exchange cancel requires live mode and live_trading_enabled=true")
    order = trade_repository.get_order_by_id(order_id)
    if not order.get("exchange_order_id"):
        updated = trade_repository.update_order(order_id, status="UNKNOWN")
        return {"status": "UNKNOWN", "order": updated, "reason": "order has no exchange order id"}
    exchange_order = await exchange_adapter.cancel_order(config, order["exchange_order_id"], order["symbol"])
    updated = trade_repository.update_order(
        order_id,
        status=exchange_order.status,
        filled_size=exchange_order.filled_size,
        remaining_size=exchange_order.remaining_size,
        average_price=exchange_order.average_price,
    )
    return {"status": updated["status"], "order": updated}


@app.get("/logs")
async def get_logs() -> list[dict]:
    return trade_repository.list_events()


@app.get("/logs/combined")
async def get_logs_combined(limit: Annotated[int, Query(ge=1, le=2000)] = 200) -> dict:
    events = trade_repository.list_events(limit=limit)
    reconciliation = trade_repository.list_reconciliation_events(unresolved_only=False, limit=limit)
    latency = trade_repository.list_latency_metrics(limit=limit)

    combined: list[dict] = []
    for ev in events:
        msg = str(ev.get("message") or "")
        category = msg.split(":", 1)[0] if ":" in msg else "system"
        combined.append({
            "timestamp": ev.get("timestamp"),
            "level": ev.get("level"),
            "category": category,
            "message": msg
        })

    for rec in reconciliation:
        combined.append({
            "timestamp": rec.get("timestamp"),
            "level": rec.get("severity"),
            "category": rec.get("kind"),
            "message": rec.get("message"),
        })

    for metric in latency:
        combined.append({
            "timestamp": metric.get("timestamp"),
            "level": "latency",
            "category": metric.get("metric"),
            "message": f'{metric.get("metric")}: {metric.get("value_ms"):.3f} ms',
        })

    combined.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    return {"logs": combined[:limit]}


@app.post("/logs/clear")
async def clear_logs(include_reconciliation: bool = True, include_latency: bool = True) -> dict:
    cleared_events = trade_repository.clear_events()
    cleared_reconciliation = trade_repository.clear_reconciliation_events() if include_reconciliation else 0
    cleared_latency = trade_repository.clear_latency_metrics() if include_latency else 0
    trade_repository.insert_event("info", "Logs cleared by user action")
    return {
        "status": "OK",
        "cleared_events": cleared_events,
        "cleared_reconciliation_events": cleared_reconciliation,
        "cleared_latency_metrics": cleared_latency,
    }


@app.websocket("/ws/live")
async def live_websocket(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        config = config_service.load(force=True)
        await websocket.send_json({
            "type": "snapshot",
            "status": trading_engine.status(),
            "pnl": pnl_payload(),
            "trades": trade_repository.list_trades(limit=50),
            "orders": trade_repository.list_orders(limit=50),
            "fills": trade_repository.list_fills(limit=50),
            "positions": trade_repository.list_positions(),
            "reconciliation": trade_repository.reconciliation_status(),
            "market_data": await market_data_engine.health(config, persist=False),
            "market": await market_data_engine.market_state(config),
            "dry_run_orders": trading_engine.status().get("dry_run_orders", []),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
