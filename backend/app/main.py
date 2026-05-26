from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .config import AppConfig, config_service
from .database import trade_repository
from .engine import trading_engine
from .websocket import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Spread System v3 API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "app://spread-system-v3"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/pnl")
async def get_pnl() -> dict:
    return pnl_payload()


@app.get("/config")
async def get_config() -> dict:
    return config_service.load(force=True).model_dump()


@app.post("/config")
async def save_config(config: AppConfig) -> dict:
    try:
        saved = config_service.save(config)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    trade_repository.insert_event("info", "Config saved and applied")
    await manager.broadcast({"type": "config", "config": saved.model_dump()})
    return saved.model_dump()


@app.post("/start")
async def start_engine() -> dict:
    return await trading_engine.start()


@app.post("/stop")
async def stop_engine() -> dict:
    return await trading_engine.stop()


@app.get("/logs")
async def get_logs() -> list[dict]:
    return trade_repository.list_events()


@app.websocket("/ws/live")
async def live_websocket(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "snapshot",
            "status": trading_engine.status(),
            "pnl": pnl_payload(),
            "trades": trade_repository.list_trades(limit=50),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
