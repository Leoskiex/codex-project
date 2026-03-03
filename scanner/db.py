from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    symbol TEXT PRIMARY KEY,
    market TEXT,
    name TEXT,
    listed INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_prices (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    turnover REAL,
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS api_usage (
    usage_date TEXT PRIMARY KEY,
    calls INTEGER NOT NULL
);
"""


@dataclass
class DailyBar:
    symbol: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


class Database:
    def __init__(self, db_path: str) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_symbols(self, symbols: Iterable[str]) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO symbols(symbol) VALUES (?)",
            [(s,) for s in symbols],
        )
        self.conn.commit()

    def upsert_bars(self, bars: Iterable[DailyBar]) -> None:
        self.conn.executemany(
            """
            INSERT INTO daily_prices(symbol, trade_date, open, high, low, close, volume, turnover)
            VALUES (:symbol, :trade_date, :open, :high, :low, :close, :volume, :turnover)
            ON CONFLICT(symbol, trade_date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                turnover=excluded.turnover
            """,
            [bar.__dict__ for bar in bars],
        )
        self.conn.commit()

    def get_symbols_missing_latest(self, max_count: int, target_date: date) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT s.symbol
            FROM symbols s
            LEFT JOIN daily_prices d
              ON d.symbol = s.symbol
             AND d.trade_date = ?
            WHERE d.symbol IS NULL
            ORDER BY s.symbol
            LIMIT ?
            """,
            (target_date.isoformat(), max_count),
        ).fetchall()
        return [r["symbol"] for r in rows]

    def top_liquidity_symbols(self, target_date: date, limit: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT symbol
            FROM daily_prices
            WHERE trade_date = ?
            ORDER BY turnover DESC, volume DESC
            LIMIT ?
            """,
            (target_date.isoformat(), limit),
        ).fetchall()
        return [r["symbol"] for r in rows]

    def load_recent_bars(self, symbol: str, lookback: int = 60) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM daily_prices
            WHERE symbol = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (symbol, lookback),
        ).fetchall()

    def close(self) -> None:
        self.conn.close()
