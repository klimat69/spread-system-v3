from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Iterator, Literal

from .config import DATA_DIR

DB_PATH = DATA_DIR / "spread_system.sqlite"

OrderStatus = Literal["NEW", "SENT", "OPEN", "PARTIAL", "FILLED", "CANCELLED", "REJECTED", "UNKNOWN"]
MarketType = Literal["spot", "swap"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def encode_raw(payload: dict[str, Any] | None) -> str:
    return json.dumps(payload or {}, sort_keys=True, default=str)


def decode_raw(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}


@dataclass(frozen=True)
class OrderIntent:
    exchange: str
    market_type: str
    symbol: str
    side: str
    order_type: str
    requested_size: float
    requested_price: float | None
    client_order_id: str


@dataclass(frozen=True)
class Order:
    exchange: str
    market_type: str
    symbol: str
    side: str
    order_type: str
    requested_size: float
    requested_price: float | None
    client_order_id: str
    exchange_order_id: str | None = None
    status: str = "NEW"
    filled_size: float = 0.0
    remaining_size: float = 0.0
    average_price: float | None = None
    raw_payload: str = "{}"
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Fill:
    exchange: str
    market_type: str
    symbol: str
    exchange_order_id: str
    exchange_trade_id: str
    side: str
    price: float
    size: float
    fee: float
    fee_currency: str
    liquidity: str | None
    timestamp: str
    raw_payload: str = "{}"


@dataclass(frozen=True)
class Position:
    exchange: str
    market_type: str
    symbol: str
    base_asset: str
    quote_asset: str
    size: float
    average_entry_price: float
    realized_pnl: float
    unrealized_pnl: float
    mark_price: float
    source: str
    last_synced_at: str


@dataclass(frozen=True)
class ReconciliationEvent:
    severity: str
    kind: str
    message: str
    exchange: str
    market_type: str
    symbol: str
    resolved: bool = False
    timestamp: str = ""


@dataclass(frozen=True)
class Trade:
    """Compatibility read/write model. Live runtime should prefer exchange-confirmed fills."""

    timestamp: str
    symbol: str
    side: str
    price: float
    size: float
    pnl: float
    fee: float
    exchange: str


class TradeRepository:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = RLock()
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._lock, self.connect() as conn:
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                requested_size REAL NOT NULL,
                requested_price REAL,
                client_order_id TEXT NOT NULL,
                exchange_order_id TEXT,
                status TEXT NOT NULL,
                filled_size REAL NOT NULL DEFAULT 0,
                remaining_size REAL NOT NULL DEFAULT 0,
                average_price REAL,
                raw_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(exchange, client_order_id)
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_exchange_order_id ON orders(exchange, exchange_order_id) WHERE exchange_order_id IS NOT NULL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange_order_id TEXT NOT NULL,
                exchange_trade_id TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                fee REAL NOT NULL DEFAULT 0,
                fee_currency TEXT NOT NULL DEFAULT '',
                liquidity TEXT,
                timestamp TEXT NOT NULL,
                raw_payload TEXT NOT NULL DEFAULT '{}',
                UNIQUE(exchange, exchange_trade_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                base_asset TEXT NOT NULL,
                quote_asset TEXT NOT NULL,
                size REAL NOT NULL,
                average_entry_price REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                mark_price REAL NOT NULL,
                source TEXT NOT NULL,
                last_synced_at TEXT NOT NULL,
                UNIQUE(exchange, market_type, symbol)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pnl_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                realized_pnl REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                fees REAL NOT NULL,
                total_pnl REAL NOT NULL,
                source TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reconciliation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                severity TEXT NOT NULL,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cooldown_until TEXT,
                last_realized_loss_at TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS validation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_data_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                sequence INTEGER,
                last_book_event_at TEXT,
                last_trade_event_at TEXT,
                measured_at_monotonic_ns INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS latency_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                metric TEXT NOT NULL,
                value_ms REAL NOT NULL,
                measured_at_monotonic_ns INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO risk_state (id, cooldown_until, last_realized_loss_at, updated_at)
            VALUES (1, NULL, NULL, ?)
        """, (utc_now(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?)", (utc_now(),))

    def create_order(self, intent: OrderIntent) -> dict:
        now = utc_now()
        order = Order(
            exchange=intent.exchange,
            market_type=intent.market_type,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            requested_size=intent.requested_size,
            requested_price=intent.requested_price,
            client_order_id=intent.client_order_id,
            remaining_size=intent.requested_size,
            created_at=now,
            updated_at=now,
        )
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO orders (
                    exchange, market_type, symbol, side, order_type, requested_size, requested_price,
                    client_order_id, exchange_order_id, status, filled_size, remaining_size,
                    average_price, raw_payload, created_at, updated_at
                ) VALUES (
                    :exchange, :market_type, :symbol, :side, :order_type, :requested_size, :requested_price,
                    :client_order_id, :exchange_order_id, :status, :filled_size, :remaining_size,
                    :average_price, :raw_payload, :created_at, :updated_at
                )
                """,
                asdict(order),
            )
            return self.get_order_by_id(cur.lastrowid, conn=conn)

    def update_order(self, local_id: int, **fields: Any) -> dict:
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        with self._lock, self.connect() as conn:
            conn.execute(f"UPDATE orders SET {assignments} WHERE id = :id", {**fields, "id": local_id})
            return self.get_order_by_id(local_id, conn=conn)

    def get_order_by_id(self, local_id: int, conn: sqlite3.Connection | None = None) -> dict:
        def read(connection: sqlite3.Connection) -> dict:
            row = connection.execute("SELECT * FROM orders WHERE id = ?", (local_id,)).fetchone()
            if row is None:
                raise KeyError(f"order {local_id} not found")
            return dict(row)

        if conn is not None:
            return read(conn)
        with self.connect() as connection:
            return read(connection)

    def get_order_by_exchange_id(self, exchange: str, exchange_order_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE exchange = ? AND exchange_order_id = ?",
                (exchange, exchange_order_id),
            ).fetchone()
            return dict(row) if row else None

    def list_orders(self, status: list[str] | None = None, symbol: str | None = None, limit: int = 500) -> list[dict]:
        query = "SELECT * FROM orders WHERE 1=1"
        params: list[Any] = []
        if status:
            query += f" AND status IN ({','.join('?' for _ in status)})"
            params.extend(status)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def upsert_fill(self, fill: Fill) -> dict | None:
        payload = asdict(fill)
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO fills (
                    exchange, market_type, symbol, exchange_order_id, exchange_trade_id, side,
                    price, size, fee, fee_currency, liquidity, timestamp, raw_payload
                ) VALUES (
                    :exchange, :market_type, :symbol, :exchange_order_id, :exchange_trade_id, :side,
                    :price, :size, :fee, :fee_currency, :liquidity, :timestamp, :raw_payload
                )
                """,
                payload,
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM fills WHERE exchange = ? AND exchange_trade_id = ?",
                (fill.exchange, fill.exchange_trade_id),
            ).fetchone()
            return dict(row)

    def list_fills(self, symbol: str | None = None, limit: int = 1000) -> list[dict]:
        query = "SELECT * FROM fills WHERE 1=1"
        params: list[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY timestamp ASC, id ASC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def upsert_position(self, position: Position) -> dict:
        payload = asdict(position)
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO positions (
                    exchange, market_type, symbol, base_asset, quote_asset, size, average_entry_price,
                    realized_pnl, unrealized_pnl, mark_price, source, last_synced_at
                ) VALUES (
                    :exchange, :market_type, :symbol, :base_asset, :quote_asset, :size, :average_entry_price,
                    :realized_pnl, :unrealized_pnl, :mark_price, :source, :last_synced_at
                )
                ON CONFLICT(exchange, market_type, symbol) DO UPDATE SET
                    base_asset = excluded.base_asset,
                    quote_asset = excluded.quote_asset,
                    size = excluded.size,
                    average_entry_price = excluded.average_entry_price,
                    realized_pnl = excluded.realized_pnl,
                    unrealized_pnl = excluded.unrealized_pnl,
                    mark_price = excluded.mark_price,
                    source = excluded.source,
                    last_synced_at = excluded.last_synced_at
                """,
                payload,
            )
            row = conn.execute(
                "SELECT * FROM positions WHERE exchange = ? AND market_type = ? AND symbol = ?",
                (position.exchange, position.market_type, position.symbol),
            ).fetchone()
            return dict(row)

    def list_positions(self, symbol: str | None = None) -> list[dict]:
        query = "SELECT * FROM positions WHERE 1=1"
        params: list[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY symbol"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def insert_pnl_snapshot(self, exchange: str, market_type: str, symbol: str, realized_pnl: float, unrealized_pnl: float, fees: float, source: str) -> dict:
        payload = {
            "exchange": exchange,
            "market_type": market_type,
            "symbol": symbol,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "fees": fees,
            "total_pnl": realized_pnl + unrealized_pnl - fees,
            "source": source,
            "timestamp": utc_now(),
        }
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO pnl_snapshots (
                    exchange, market_type, symbol, realized_pnl, unrealized_pnl, fees, total_pnl, source, timestamp
                ) VALUES (
                    :exchange, :market_type, :symbol, :realized_pnl, :unrealized_pnl, :fees, :total_pnl, :source, :timestamp
                )
                """,
                payload,
            )
            return {"id": cur.lastrowid, **payload}

    def latest_pnl_snapshot(self, symbol: str | None = None) -> dict:
        query = "SELECT * FROM pnl_snapshots"
        params: list[Any] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY timestamp DESC, id DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row:
            return dict(row)
        return {
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "fees": 0.0,
            "total_pnl": 0.0,
            "source": "none",
            "timestamp": None,
        }

    def latest_pnl_snapshots(self, symbol: str | None = None, limit: int = 2) -> list[dict]:
        query = "SELECT * FROM pnl_snapshots"
        params: list[Any] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def pnl_summary(self) -> dict:
        snapshot = self.latest_pnl_snapshot()
        fills = self.list_fills(limit=5000)
        running = 0.0
        inventory: dict[str, tuple[float, float]] = {}
        equity = []
        for fill in fills:
            symbol = fill["symbol"]
            current_size, avg_entry = inventory.get(symbol, (0.0, 0.0))
            size = float(fill["size"])
            price = float(fill["price"])
            if fill["side"] == "buy":
                new_size = current_size + size
                avg_entry = ((current_size * avg_entry) + (size * price)) / new_size if new_size else 0.0
                current_size = new_size
            elif fill["side"] == "sell" and current_size > 0:
                closing = min(current_size, size)
                running += (price - avg_entry) * closing
                current_size -= closing
                if current_size == 0:
                    avg_entry = 0.0
            running -= float(fill["fee"])
            inventory[symbol] = (current_size, avg_entry)
            equity.append({"timestamp": fill["timestamp"], "equity": running})
        total = float(snapshot["total_pnl"])
        return {
            "gross_pnl": float(snapshot["realized_pnl"]) + float(snapshot["unrealized_pnl"]),
            "fees": float(snapshot["fees"]),
            "net_pnl": total,
            "total_pnl": total,
            "realized_pnl": float(snapshot["realized_pnl"]),
            "unrealized_pnl": float(snapshot["unrealized_pnl"]),
            "trade_count": len(fills),
            "winrate": 0.0,
            "profit_factor": 0.0,
            "equity_curve": equity,
            "source": snapshot["source"],
            "timestamp": snapshot["timestamp"],
        }

    def daily_pnl(self, day: datetime | None = None) -> float:
        day = day or datetime.now(UTC)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        with self.connect() as conn:
            end_row = conn.execute(
                """
                SELECT total_pnl FROM pnl_snapshots
                WHERE timestamp <= ?
                ORDER BY timestamp DESC, id DESC LIMIT 1
                """,
                (end,),
            ).fetchone()
            start_row = conn.execute(
                """
                SELECT total_pnl FROM pnl_snapshots
                WHERE timestamp < ?
                ORDER BY timestamp DESC, id DESC LIMIT 1
                """,
                (start,),
            ).fetchone()
        end_total = float(end_row["total_pnl"]) if end_row else 0.0
        start_total = float(start_row["total_pnl"]) if start_row else 0.0
        return end_total - start_total

    def insert_reconciliation_event(self, event: ReconciliationEvent) -> dict:
        payload = asdict(event)
        payload["timestamp"] = payload["timestamp"] or utc_now()
        payload["resolved"] = int(payload["resolved"])
        with self._lock, self.connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM reconciliation_events
                WHERE severity = :severity
                  AND kind = :kind
                  AND message = :message
                  AND exchange = :exchange
                  AND market_type = :market_type
                  AND symbol = :symbol
                  AND resolved = 0
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                payload,
            ).fetchone()
            if existing:
                return dict(existing)
            cur = conn.execute(
                """
                INSERT INTO reconciliation_events (
                    timestamp, severity, kind, message, exchange, market_type, symbol, resolved
                ) VALUES (
                    :timestamp, :severity, :kind, :message, :exchange, :market_type, :symbol, :resolved
                )
                """,
                payload,
            )
            return {"id": cur.lastrowid, **payload}

    def list_reconciliation_events(self, unresolved_only: bool = False, limit: int = 200) -> list[dict]:
        query = "SELECT * FROM reconciliation_events WHERE 1=1"
        params: list[Any] = []
        if unresolved_only:
            query += " AND resolved = 0"
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def resolve_reconciliation_events(self, exchange: str, market_type: str, symbol: str, kind: str | None = None) -> int:
        query = """
            UPDATE reconciliation_events
            SET resolved = 1
            WHERE exchange = ? AND market_type = ? AND symbol = ? AND resolved = 0
        """
        params: list[Any] = [exchange, market_type, symbol]
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        with self._lock, self.connect() as conn:
            cur = conn.execute(query, params)
            return cur.rowcount

    def reconciliation_status(self) -> dict:
        unresolved = self.list_reconciliation_events(unresolved_only=True, limit=50)
        blocking = [event for event in unresolved if event["severity"].upper() in {"HIGH", "CRITICAL"}]
        latest = unresolved[0] if unresolved else None
        return {
            "status": "FAILED" if blocking else "OK",
            "blocking": bool(blocking),
            "unresolved_count": len(unresolved),
            "latest_event": latest,
        }

    def get_risk_state(self) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM risk_state WHERE id = 1").fetchone()
            return dict(row)

    def insert_market_data_health(
        self,
        exchange: str,
        market_type: str,
        symbol: str,
        status: str,
        reason: str,
        sequence: int | None,
        last_book_event_at: str | None,
        last_trade_event_at: str | None,
        measured_at_monotonic_ns: int,
    ) -> dict:
        payload = {
            "exchange": exchange,
            "market_type": market_type,
            "symbol": symbol,
            "status": status,
            "reason": reason,
            "sequence": sequence,
            "last_book_event_at": last_book_event_at,
            "last_trade_event_at": last_trade_event_at,
            "measured_at_monotonic_ns": measured_at_monotonic_ns,
            "timestamp": utc_now(),
        }
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO market_data_health (
                    exchange, market_type, symbol, status, reason, sequence, last_book_event_at,
                    last_trade_event_at, measured_at_monotonic_ns, timestamp
                ) VALUES (
                    :exchange, :market_type, :symbol, :status, :reason, :sequence, :last_book_event_at,
                    :last_trade_event_at, :measured_at_monotonic_ns, :timestamp
                )
                """,
                payload,
            )
            return {"id": cur.lastrowid, **payload}

    def latest_market_data_health(self, exchange: str | None = None, market_type: str | None = None, symbol: str | None = None) -> dict:
        query = "SELECT * FROM market_data_health WHERE 1=1"
        params: list[Any] = []
        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)
        if market_type:
            query += " AND market_type = ?"
            params.append(market_type)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY timestamp DESC, id DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else {"status": "UNINITIALIZED", "reason": "market data engine has not reported health"}

    def insert_latency_metric(
        self,
        exchange: str,
        market_type: str,
        symbol: str,
        metric: str,
        value_ms: float,
        measured_at_monotonic_ns: int,
    ) -> dict:
        payload = {
            "exchange": exchange,
            "market_type": market_type,
            "symbol": symbol,
            "metric": metric,
            "value_ms": value_ms,
            "measured_at_monotonic_ns": measured_at_monotonic_ns,
            "timestamp": utc_now(),
        }
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO latency_metrics (
                    exchange, market_type, symbol, metric, value_ms, measured_at_monotonic_ns, timestamp
                ) VALUES (
                    :exchange, :market_type, :symbol, :metric, :value_ms, :measured_at_monotonic_ns, :timestamp
                )
                """,
                payload,
            )
            return {"id": cur.lastrowid, **payload}

    def list_latency_metrics(self, exchange: str | None = None, market_type: str | None = None, symbol: str | None = None, limit: int = 200) -> list[dict]:
        query = "SELECT * FROM latency_metrics WHERE 1=1"
        params: list[Any] = []
        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)
        if market_type:
            query += " AND market_type = ?"
            params.append(market_type)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def insert_validation_result(self, exchange: str, market_type: str, symbol: str, status: str, message: str, details: dict[str, Any] | None = None) -> dict:
        payload = {
            "exchange": exchange,
            "market_type": market_type,
            "symbol": symbol,
            "status": status,
            "message": message,
            "details": encode_raw(details),
            "timestamp": utc_now(),
        }
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO validation_results (exchange, market_type, symbol, status, message, details, timestamp)
                VALUES (:exchange, :market_type, :symbol, :status, :message, :details, :timestamp)
                """,
                payload,
            )
            return {"id": cur.lastrowid, **payload}

    def latest_validation_result(self, exchange: str, market_type: str, symbol: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM validation_results
                WHERE exchange = ? AND market_type = ? AND symbol = ?
                ORDER BY timestamp DESC, id DESC LIMIT 1
                """,
                (exchange, market_type, symbol),
            ).fetchone()
            if row:
                result = dict(row)
                result["details"] = decode_raw(result.get("details"))
                return result
        return {
            "status": "BLOCKED_NO_CREDENTIALS",
            "message": "No exchange validation has passed for this exchange/symbol/market type.",
            "timestamp": None,
            "details": {},
        }

    def update_risk_state(self, cooldown_until: str | None, last_realized_loss_at: str | None) -> dict:
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                UPDATE risk_state
                SET cooldown_until = ?, last_realized_loss_at = ?, updated_at = ?
                WHERE id = 1
                """,
                (cooldown_until, last_realized_loss_at, utc_now()),
            )
            row = conn.execute("SELECT * FROM risk_state WHERE id = 1").fetchone()
            return dict(row)

    def insert_trade(self, trade: Trade) -> dict:
        fill = Fill(
            exchange=trade.exchange,
            market_type="spot",
            symbol=trade.symbol,
            exchange_order_id=f"legacy-{trade.timestamp}",
            exchange_trade_id=f"legacy-{trade.timestamp}-{trade.side}-{trade.size}",
            side=trade.side,
            price=trade.price,
            size=trade.size,
            fee=trade.fee,
            fee_currency="",
            liquidity=None,
            timestamp=trade.timestamp,
            raw_payload=encode_raw({"legacy_pnl": trade.pnl}),
        )
        return self.upsert_fill(fill) or {"id": None, **asdict(trade)}

    def list_trades(self, symbol: str | None = None, start: str | None = None, end: str | None = None, limit: int = 500) -> list[dict]:
        query = "SELECT * FROM fills WHERE 1=1"
        params: list[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "symbol": row["symbol"],
                "side": row["side"],
                "price": row["price"],
                "size": row["size"],
                "pnl": 0.0,
                "fee": row["fee"],
                "exchange": row["exchange"],
                "order_id": row["exchange_order_id"],
                "trade_id": row["exchange_trade_id"],
            }
            for row in rows
        ]

    def insert_event(self, level: str, message: str) -> dict:
        event = {"timestamp": utc_now(), "level": level, "message": message}
        with self._lock, self.connect() as conn:
            cur = conn.execute("INSERT INTO events (timestamp, level, message) VALUES (:timestamp, :level, :message)", event)
            return {"id": cur.lastrowid, **event}

    def list_events(self, limit: int = 200) -> list[dict]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()]

    def clear_events(self) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute("DELETE FROM events")
            return int(cur.rowcount or 0)

    def clear_reconciliation_events(self) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute("DELETE FROM reconciliation_events")
            return int(cur.rowcount or 0)

    def clear_latency_metrics(self) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute("DELETE FROM latency_metrics")
            return int(cur.rowcount or 0)


trade_repository = TradeRepository()
