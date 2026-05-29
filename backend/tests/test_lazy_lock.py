import asyncio

import pytest

from app.broadcast import connection_manager
from app.lazy_lock import LazyAsyncLock
from app.market_data import market_data_engine


def test_module_singleton_locks_are_lazy_at_import() -> None:
    assert isinstance(connection_manager._lock, LazyAsyncLock)
    assert connection_manager._lock._lock is None
    assert isinstance(market_data_engine._lock, LazyAsyncLock)
    assert market_data_engine._lock._lock is None


@pytest.mark.anyio
async def test_lazy_async_lock_works_under_running_loop() -> None:
    lock = LazyAsyncLock()
    async with lock:
        assert lock.locked()
    assert not lock.locked()


@pytest.mark.anyio
async def test_connection_manager_lock_after_first_use() -> None:
    async with connection_manager._lock:
        assert connection_manager._lock._lock is not None
