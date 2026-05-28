from __future__ import annotations

import os
import signal
import sys
from pathlib import Path


def _configure_sys_path() -> None:
    # In development mode this file runs from backend/app/server_entrypoint.py.
    # Add backend root so absolute imports like `app.main` resolve.
    if getattr(sys, "frozen", False):
        return
    backend_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_root))


def _run() -> int:
    _configure_sys_path()

    import uvicorn  # noqa: PLC0415 (runtime import is required after sys.path wiring)

    from app.main import app  # noqa: PLC0415

    host = os.environ.get("SPREAD_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("SPREAD_BACKEND_PORT", "8000"))

    # Graceful shutdown: uvicorn handles signals, but pyinstaller entrypoints can vary.
    def _handle_sigterm(*_: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())

