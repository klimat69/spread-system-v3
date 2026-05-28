from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        async with self._lock:
            connections = list(self.active_connections)
        for websocket in connections:
            asyncio.create_task(self._send_or_drop(websocket, payload))

    async def _send_or_drop(self, websocket: WebSocket, payload: dict) -> None:
        try:
            await asyncio.wait_for(websocket.send_json(payload), timeout=0.25)
        except Exception:
            logger.exception("Dropping failed websocket connection")
            await self.disconnect(websocket)


connection_manager = ConnectionManager()
