from __future__ import annotations

from scanner.db import DailyBar


class YFinanceClient:
    """Yahoo Finance data client for TW stocks."""

    def get_historical_bars(self, symbol: str, period: str = "1y") -> list[DailyBar]:
        import yfinance as yf

        frame = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False)
        if frame.empty:
            return []

        bars: list[DailyBar] = []
        for idx, row in frame.iterrows():
            trade_date = idx.date().isoformat()
            close = float(row["Close"])
            volume = float(row.get("Volume", 0) or 0)
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=close,
                    volume=volume,
                    turnover=close * volume,
                )
            )
        return bars

    def get_latest_bar(self, symbol: str) -> DailyBar | None:
        bars = self.get_historical_bars(symbol=symbol, period="7d")
        return bars[-1] if bars else None
