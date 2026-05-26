# Spread System v3

Spread System v3 is a production-oriented spread trading system with a FastAPI backend, React trading dashboard, SQLite trade history, WebSocket live updates, CCXT exchange abstraction, risk controls, and an Electron desktop wrapper.

## Safety Defaults

The default runtime is paper mode. Live trading is blocked unless all of these are true in `data/config.json` or the UI config panel:

- `trading.mode` is `live`
- `trading.live_trading_enabled` is `true`
- valid exchange credentials are configured

If strategy, volatility, liquidity, or risk checks fail, the engine does nothing and broadcasts the block reason.

## Features

- CCXT exchange adapter for Binance, Bybit, and MEXC.
- Fee-aware spread strategy: `edge = spread - (maker + taker)`.
- Risk engine with max daily loss, max inventory exposure, max position size, and cooldown after losses.
- SQLite `trades` table with `timestamp`, `symbol`, `side`, `price`, `size`, `pnl`, `fee`, and `exchange`.
- FastAPI endpoints: `GET /status`, `GET /trades`, `GET /pnl`, `GET /config`, `POST /config`, `POST /start`, `POST /stop`, and `WS /ws/live`.
- React dashboard with live PnL, equity curve, spread/edge/volatility panels, bot status, config editor, logs, and filtered trade history.
- Electron desktop app with installer targets for Windows, macOS, and Linux.

## Project Layout

```text
backend/     FastAPI API, engine, strategy, risk, CCXT, SQLite
frontend/    React/Vite dashboard
desktop/     Electron app wrapper
installer/   Electron Builder config and installer notes
data/        Runtime config and SQLite database
run.py       Local dev launcher
```

## Local Setup

Requirements: Python 3.11+, Node.js 20+, and npm.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
npm --prefix desktop install
```

Run dev mode:

```bash
python run.py
```

Open the dashboard at `http://127.0.0.1:5173`.

## Backend And Frontend

Standalone backend:

```bash
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Standalone frontend:

```bash
npm --prefix frontend run dev
```

Production frontend build:

```bash
npm --prefix frontend run build
```

## Configuration

Runtime config lives in `data/config.json` and can also be edited in the dashboard. All exchange, API key, fee, symbol, threshold, risk, and order-size values are loaded from config. The engine reloads config on every cycle, so saved dashboard changes apply without restarting the backend.

## Strategy Loop

Every cycle:

1. Fetch the configured exchange order book through CCXT.
2. Calculate spread, imbalance, liquidity, volatility, and fee-aware edge.
3. Require `edge = spread - (maker + taker)` to exceed `strategy.min_edge`.
4. Apply volatility, imbalance, liquidity, and risk filters.
5. Execute only if all checks pass.
6. Save trades to SQLite and broadcast live updates through WebSocket.

## VPS Deployment

```bash
git clone <your-repo-url> spread-system-v3
cd spread-system-v3
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Serve `frontend/dist` through Nginx/Caddy and reverse proxy `/status`, `/trades`, `/pnl`, `/config`, `/start`, `/stop`, `/logs`, and `/ws` to the FastAPI backend.

## Desktop App And Installers

Development desktop mode expects backend dependencies installed and the frontend dev server running:

```bash
npm --prefix frontend run dev
npm --prefix desktop run dev
```

Installer targets:

```bash
npm --prefix desktop run build:win
npm --prefix desktop run build:mac
npm --prefix desktop run build:linux
```

Expected artifacts under `installer/dist`:

- Windows: `spread-system-v3-setup.exe`
- macOS: `spread-system-v3.dmg`
- Linux: `spread-system-v3.AppImage`

The Windows NSIS installer is configured for EN/RU installer languages, selectable install path, Start Menu shortcut, and desktop shortcut creation.

## Tests

```bash
PYTHONPATH=. pytest
npm --prefix frontend run build
hdiutil verify installer/dist/spread-system-v3.dmg
```

## GitHub Setup

After the first commit, the intended automatic repository setup is:

```bash
gh repo create spread-system-v3 --public --source=. --remote=origin --push
```

If GitHub CLI is unavailable or not authenticated, create a public GitHub repo named `spread-system-v3`, then run:

```bash
git remote add origin <your-repo-url>
git push -u origin main
```
