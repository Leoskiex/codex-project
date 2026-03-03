from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scanner.db import DailyBar
from scanner.rate_limiter import CompositeRateLimiter


class FugleClient:
    def __init__(self, api_key: str, base_url: str, limiter: CompositeRateLimiter) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.limiter = limiter

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.limiter.acquire()
        query = urlencode({**params, "apiToken": self.api_key})
        url = f"{self.base_url}{path}?{query}"
        req = Request(url, method="GET")

        with urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8")
        return json.loads(data)

    def get_historical_bars(self, symbol: str) -> list[DailyBar]:
        payload = self._get(f"/marketdata/v1.0/stock/historical/candles/{symbol}", {})
        data = payload.get("data", [])
        bars: list[DailyBar] = []
        for row in data:
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=row["date"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                    turnover=float(row.get("amount", 0)),
                )
            )
        return bars

    def get_latest_bar(self, symbol: str) -> DailyBar | None:
        payload = self._get(f"/marketdata/v1.0/stock/intraday/candles/{symbol}", {"timeframe": "D"})
        data = payload.get("data", [])
        if not data:
            return None
        last = data[-1]
        return DailyBar(
            symbol=symbol,
            trade_date=last["date"],
            open=float(last["open"]),
            high=float(last["high"]),
            low=float(last["low"]),
            close=float(last["close"]),
            volume=float(last.get("volume", 0)),
            turnover=float(last.get("amount", 0)),
        )
