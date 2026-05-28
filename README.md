# Spread System v3

Spread System v3 is a production-oriented spread trading system with a FastAPI backend, React trading dashboard, SQLite trade history, WebSocket live updates, CCXT exchange abstraction, risk controls, and an Electron desktop wrapper.

## Safety Defaults

The default runtime is paper mode. Live trading is blocked unless all of these are true in local `data/config.json` or the UI config panel:

- `trading.mode` is `live`
- `trading.live_trading_enabled` is `true`
- the latest validation result for the exchange/symbol/market type is `PASSED`
- valid exchange credentials are configured

If strategy, volatility, liquidity, or risk checks fail, the engine does nothing and broadcasts the block reason.

## Features

- CCXT exchange adapter for Binance, Bybit, and MEXC.
- DOM/orderflow microscalping strategy using orderbook imbalance, liquidity walls, tape aggression, and short holding windows.
- Risk engine with max daily loss, max inventory exposure, max position size, and cooldown after losses.
- SQLite order, fill, position, PnL, reconciliation, validation, and risk-state ledgers.
- FastAPI endpoints for status, config, orders, fills, positions, PnL, reconciliation, sync, order cancel, logs, and WebSocket live state.
- React dashboard with live PnL, equity curve, orderflow metrics, liquidity walls, bot status, order/fill/position tables, reconciliation state, config editor, and logs.
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
cp data/config.example.json data/config.json
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

Runtime config lives in local `data/config.json` and can also be edited in the dashboard. Start from `data/config.example.json`; do not commit `data/config.json` because it can contain live API keys. All exchange, API key, fee, symbol, threshold, risk, and order-size values are loaded from config. The engine reloads config on every cycle, so saved dashboard changes apply without restarting the backend.

## Real Trading Safety Gate

Live order submission is blocked unless the exchange validation gate passes for the configured exchange, symbol, and market type. `trading.live_trading_enabled: true` is not enough by itself.

Run validation after configuring real exchange credentials:

```bash
cd backend
../.venv/bin/python -m app.validate_exchange --symbol BTC/USDT --market-type spot
```

Without credentials the validator records `BLOCKED_NO_CREDENTIALS`, and the engine keeps live trading blocked. The validator checks local orders, exchange orders, exchange-confirmed fills, balances/positions, and reconciliation state.

## Strategy Loop

Every cycle:

1. Fetch configured exchange orderbook depth and recent public trades through CCXT.
2. Calculate weighted bid/ask pressure, orderbook imbalance, liquidity walls, tape aggression, momentum burst ratio, liquidity, and volatility.
3. Enter only when DOM imbalance, tape aggression, and momentum burst align; spread is not treated as guaranteed profit.
4. Exit open micro positions immediately when imbalance weakens, tape flips/fades, a supporting wall disappears, or max holding time is reached.
5. Create a durable order intent only if reconciliation, validation, and risk checks pass.
6. Submit the order and wait for exchange order/trade sync before recording fills or PnL.
7. Rebuild positions and PnL only from exchange-confirmed fills and exchange position/balance data.

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

Serve `frontend/dist` through Nginx/Caddy and reverse proxy the FastAPI API plus `/ws` to the backend.

## Desktop App And Installers
End users should install and launch the app without any terminal commands.

### Install (Windows/macOS/Linux)
1. Download the installer artifact for your OS (from your release build / CI artifacts).
2. Run the installer (`.exe` / `.dmg` / `.AppImage`).
3. Launch `Spread System v3` from the desktop icon or Start Menu / Applications.
4. On first launch, complete the in-app setup wizard:
   1. Select exchange (MEXC / Bybit / Binance).
   2. Paste API key + secret (stored securely in your OS keychain).
   3. Choose paper mode (default) or live mode (locked until the connectivity test passes).
   4. Select trading pair and market type.
   5. Run connectivity test (websocket feed health + exchange validation).

### Paper Mode
Paper mode is available immediately after the wizard. The dashboard still shows live DOM/tape signals and order/execution history.

### Live Mode Safety Gate
Live mode stays blocked unless all of these are true:
- exchange validation passes
- reconciliation is not blocking
- websocket market-data feed health is OK (no stale / no gaps)

### Logs
The dashboard includes a local log center with:
- export logs (download JSON)
- clear logs

### Developer Mode (optional)
If you are building locally, desktop dev mode expects the backend runtime dependencies and the frontend dev server:

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
