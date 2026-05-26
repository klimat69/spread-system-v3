from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def spawn(name: str, command: list[str], cwd: Path) -> subprocess.Popen[str]:
    print(f"[run.py] starting {name}: {' '.join(command)}")
    return subprocess.Popen(
        command,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
    )


def main() -> int:
    frontend_node_modules = ROOT / "frontend" / "node_modules"
    if not frontend_node_modules.exists():
        print("[run.py] frontend dependencies missing. Run: npm --prefix frontend install")
    print("[run.py] backend dependencies: python -m pip install -r requirements.txt")

    processes = [
        spawn(
            "backend",
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
            ROOT,
        ),
        spawn("frontend", ["npm", "run", "dev", "--", "--host", "127.0.0.1"], ROOT / "frontend"),
    ]

    def shutdown(*_: object) -> None:
        print("\n[run.py] stopping services")
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while any(process.poll() is None for process in processes):
            time.sleep(0.5)
    finally:
        shutdown()

    return max((process.returncode or 0) for process in processes)


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def start_process(name: str, command: list[str], cwd: Path, env: dict | None = None) -> subprocess.Popen:
    print(f"[spread-system-v3] starting {name}: {' '.join(command)}")
    return subprocess.Popen(command, cwd=cwd, env={**os.environ, **(env or {})})


def main() -> int:
    processes: list[subprocess.Popen] = []
    try:
        backend_env = {"PYTHONPATH": str(BACKEND)}
        processes.append(
            start_process(
                "backend",
                [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
                BACKEND,
                backend_env,
            )
        )
        processes.append(start_process("frontend", ["npm", "run", "dev"], FRONTEND))
        print("[spread-system-v3] dashboard: http://127.0.0.1:5173")
        while all(process.poll() is None for process in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[spread-system-v3] shutting down")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
