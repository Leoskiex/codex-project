from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scanner.db import DailyBar, Database
from scanner.fugle_client import FugleClient


@dataclass
class Candidate:
    symbol: str
    total_score: float
    score_v2: float
    score_v3: float
    pivot_bonus: float
    status: str


class StrategyEngine:
    """v2/v3 + Pivot Points integrated scoring model."""

    def score_components(self, bars: list[DailyBar]) -> tuple[float, float, float]:
        # Expect bars sorted with latest bar first.
        if len(bars) < 60:
            return 0.0, 0.0, 0.0

        today = bars[0]
        prev = bars[1]

        recent_5 = bars[:5]
        prior_20 = bars[1:21]
        sma20_window = bars[:20]
        sma60_window = bars[:60]

        low_20d = min(b.low for b in prior_20)
        high_20d = max(b.high for b in prior_20)
        avg_volume_5 = sum(b.volume for b in recent_5) / 5

        sma20 = sum(b.close for b in sma20_window) / 20
        sma60 = sum(b.close for b in sma60_window) / 60

        # v2: absorption / false breakdown reclaim + volume surge.
        absorption = (
            today.low < low_20d
            and today.close > low_20d
            and today.volume > avg_volume_5 * 1.5
        )
        score_v2 = 30.0 if absorption else 0.0

        # v3: trend + breakout + volume confirmation with continuation bonuses.
        trend = today.close > sma20 and sma20 > sma60
        breakout = today.close >= high_20d
        volume_confirm = today.volume > avg_volume_5

        score_v3 = 0.0
        if trend and breakout and volume_confirm:
            score_v3 = 40.0
            if len(bars) >= 4 and today.low > bars[3].low:
                score_v3 += 10.0

            bullish_days = sum(1 for b in recent_5 if b.close > b.open) >= 3
            if bullish_days:
                score_v3 += 10.0

        # Pivot points from previous day.
        p = (prev.high + prev.low + prev.close) / 3
        s1 = 2 * p - prev.high
        s2 = p - (prev.high - prev.low)

        pivot_bonus = 0.0
        if today.close <= s2:
            pivot_bonus += 15.0
        elif today.close <= s1:
            pivot_bonus += 10.0

        if today.close > p:
            pivot_bonus += 5.0

        return score_v2, score_v3, pivot_bonus

    def score(self, bars: list[DailyBar]) -> tuple[float, float, float, float, str]:
        score_v2, score_v3, pivot_bonus = self.score_components(bars)
        total_score = score_v2 + score_v3 + pivot_bonus
        status = "Strong Candidate" if total_score >= 70 else "Watch Only"
        return total_score, score_v2, score_v3, pivot_bonus, status


class ScannerPipeline:
    def __init__(self, db: Database, client: FugleClient) -> None:
        self.db = db
        self.client = client
        self.strategy = StrategyEngine()

    def bootstrap_batch(self, symbols: list[str], batch_size: int) -> int:
        selected = symbols[:batch_size]
        self.db.upsert_symbols(selected)

        updated = 0
        for symbol in selected:
            bars = self.client.get_historical_bars(symbol)
            if bars:
                self.db.upsert_bars(bars)
                updated += 1
        return updated

    def refresh_latest_bars(self, symbols: list[str]) -> int:
        bars_to_upsert: list[DailyBar] = []
        for symbol in symbols:
            bar = self.client.get_latest_bar(symbol)
            if bar:
                bars_to_upsert.append(bar)

        if bars_to_upsert:
            self.db.upsert_bars(bars_to_upsert)
        return len(bars_to_upsert)

    def run_daily_scan(self, top_liquidity: int, top_candidates: int, target_date: date) -> list[Candidate]:
        liquidity_symbols = self.db.top_liquidity_symbols(target_date=target_date, limit=top_liquidity)

        candidates: list[Candidate] = []
        for symbol in liquidity_symbols:
            rows = self.db.load_recent_bars(symbol)
            bars = [
                DailyBar(
                    symbol=row["symbol"],
                    trade_date=row["trade_date"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    turnover=row["turnover"],
                )
                for row in rows
            ]
            total_score, score_v2, score_v3, pivot_bonus, status = self.strategy.score(bars)
            if total_score > 0:
                candidates.append(
                    Candidate(
                        symbol=symbol,
                        total_score=total_score,
                        score_v2=score_v2,
                        score_v3=score_v3,
                        pivot_bonus=pivot_bonus,
                        status=status,
                    )
                )

        return sorted(candidates, key=lambda c: c.total_score, reverse=True)[:top_candidates]
