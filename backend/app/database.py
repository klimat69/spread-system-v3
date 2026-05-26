from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Iterator

from .config import DATA_DIR

DB_PATH = DATA_DIR / "spread_system.sqlite"


@dataclass(frozen=True)
class Trade:
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    size REAL NOT NULL,
                    pnl REAL NOT NULL,
                    fee REAL NOT NULL,
                    exchange TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                )
            """)

    def insert_trade(self, trade: Trade) -> dict:
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO trades (timestamp, symbol, side, price, size, pnl, fee, exchange)
                   VALUES (:timestamp, :symbol, :side, :price, :size, :pnl, :fee, :exchange)""",
                asdict(trade),
            )
            return {"id": cur.lastrowid, **asdict(trade)}

    def list_trades(self, symbol: str | None = None, start: str | None = None, end: str | None = None, limit: int = 500) -> list[dict]:
        query = "SELECT * FROM trades WHERE 1=1"
        params: list[str | int] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def pnl_summary(self) -> dict:
        with self.connect() as conn:
            rows = conn.execute("SELECT timestamp, pnl, fee FROM trades ORDER BY timestamp ASC").fetchall()
        gross = sum(float(row["pnl"]) for row in rows)
        fees = sum(float(row["fee"]) for row in rows)
        wins = [float(row["pnl"]) for row in rows if float(row["pnl"]) > 0]
        losses = [abs(float(row["pnl"])) for row in rows if float(row["pnl"]) < 0]
        running = 0.0
        equity = []
        for row in rows:
            running += float(row["pnl"]) - float(row["fee"])
            equity.append({"timestamp": row["timestamp"], "equity": running})
        total = len(rows)
        return {
            "gross_pnl": gross,
            "fees": fees,
            "net_pnl": gross - fees,
            "trade_count": total,
            "winrate": len(wins) / total if total else 0.0,
            "profit_factor": sum(wins) / sum(losses) if losses else (sum(wins) if wins else 0.0),
            "equity_curve": equity,
        }

    def daily_pnl(self, day: datetime | None = None) -> float:
        day = day or datetime.now(UTC)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        with self.connect() as conn:
            row = conn.execute("SELECT COALESCE(SUM(pnl - fee), 0) AS pnl FROM trades WHERE timestamp BETWEEN ? AND ?", (start, end)).fetchone()
        return float(row["pnl"])

    def insert_event(self, level: str, message: str) -> dict:
        event = {"timestamp": datetime.now(UTC).isoformat(), "level": level, "message": message}
        with self._lock, self.connect() as conn:
            cur = conn.execute("INSERT INTO events (timestamp, level, message) VALUES (:timestamp, :level, :message)", event)
            return {"id": cur.lastrowid, **event}

    def list_events(self, limit: int = 200) -> list[dict]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()]


trade_repository = TradeRepository()
