from __future__ import annotations

import asyncio


class LazyAsyncLock:
    """Create asyncio.Lock on first use inside the active event loop."""

    __slots__ = ("_lock",)

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None

    def _get(self) -> asyncio.Lock:
        lock = self._lock
        if lock is None:
            lock = asyncio.Lock()
            self._lock = lock
        return lock

    async def __aenter__(self) -> None:
        await self._get().__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._get().__aexit__(exc_type, exc, tb)

    def locked(self) -> bool:
        if self._lock is None:
            return False
        return self._lock.locked()
