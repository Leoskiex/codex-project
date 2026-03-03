from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scanner.db import DailyBar, Database
from scanner.fugle_client import YFinanceClient


@dataclass
class Candidate:
    symbol: str
    total_score: float
    score_v2: float
    score_v3: float
    pivot_bonus: float
    status: str


@dataclass
class QualityPick:
    symbol: str
    momentum_90d: float


@dataclass
class QualitySimulationResult:
    rebalance_dates: list[date]
    portfolio_values: list[float]
    latest_picks: list[QualityPick]
    selection_return_by_symbol: dict[str, float]


@dataclass
class MomentumSpectrumRow:
    symbol: str
    m7: float
    m14: float
    m21: float
    m30: float
    m60: float
    m90: float
    trend_state: str


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


class QualityStrategy:
    """90-day momentum quality strategy with monthly rebalance."""

    def __init__(self, lookback_days: int = 90, threshold: float = 0.15, top_n: int = 10) -> None:
        self.lookback_days = lookback_days
        self.threshold = threshold
        self.top_n = top_n

    def _month_starts(self, all_dates: list[date]) -> list[date]:
        starts: list[date] = []
        seen: set[tuple[int, int]] = set()
        for d in sorted(all_dates):
            key = (d.year, d.month)
            if key not in seen:
                seen.add(key)
                starts.append(d)
        return starts

    def _value_on_or_before(self, series: list[tuple[date, float]], target: date) -> tuple[int, float] | None:
        pos = -1
        for i, (d, _) in enumerate(series):
            if d <= target:
                pos = i
            else:
                break
        if pos < 0:
            return None
        return pos, series[pos][1]

    def picks_for_date(self, close_series: dict[str, list[tuple[date, float]]], as_of: date) -> list[QualityPick]:
        picks: list[QualityPick] = []
        for symbol, series in close_series.items():
            point = self._value_on_or_before(series, as_of)
            if point is None:
                continue
            idx, close_now = point
            if idx < self.lookback_days:
                continue

            close_then = series[idx - self.lookback_days][1]
            if close_then <= 0:
                continue

            momentum = (close_now / close_then) - 1
            if momentum > self.threshold:
                picks.append(QualityPick(symbol=symbol, momentum_90d=momentum))

        picks.sort(key=lambda p: p.momentum_90d, reverse=True)
        return picks[: self.top_n]

    def momentum_spectrum_for_date(
        self,
        close_series: dict[str, list[tuple[date, float]]],
        as_of: date,
    ) -> list[MomentumSpectrumRow]:
        def _mom(series: list[tuple[date, float]], idx: int, lookback: int) -> float | None:
            if idx < lookback:
                return None
            now = series[idx][1]
            then = series[idx - lookback][1]
            if then <= 0:
                return None
            return (now / then) - 1

        rows: list[MomentumSpectrumRow] = []
        for symbol, series in close_series.items():
            point = self._value_on_or_before(series, as_of)
            if point is None:
                continue

            idx, _ = point
            momentums = {
                7: _mom(series, idx, 7),
                14: _mom(series, idx, 14),
                21: _mom(series, idx, 21),
                30: _mom(series, idx, 30),
                60: _mom(series, idx, 60),
                90: _mom(series, idx, 90),
            }
            if any(v is None for v in momentums.values()):
                continue

            m7 = float(momentums[7])
            m14 = float(momentums[14])
            m21 = float(momentums[21])
            m30 = float(momentums[30])
            m60 = float(momentums[60])
            m90 = float(momentums[90])

            if m7 > m14 > m21 > m30 > m60 > m90:
                trend_state = "Increasing"
            elif m7 < m14 < m21 < m30:
                trend_state = "Dropping Off"
            else:
                trend_state = "Mixed"

            rows.append(
                MomentumSpectrumRow(
                    symbol=symbol,
                    m7=m7,
                    m14=m14,
                    m21=m21,
                    m30=m30,
                    m60=m60,
                    m90=m90,
                    trend_state=trend_state,
                )
            )

        rows.sort(key=lambda r: r.m90, reverse=True)
        return rows

    def simulate(self, close_series: dict[str, list[tuple[date, float]]]) -> QualitySimulationResult:
        all_dates = sorted({d for series in close_series.values() for d, _ in series})
        rebalance_dates = self._month_starts(all_dates)
        if len(rebalance_dates) < 2:
            return QualitySimulationResult([], [1.0], [], {})

        portfolio_values: list[float] = [1.0]
        selection_return_by_symbol: dict[str, float] = {}
        latest_picks: list[QualityPick] = []

        for i in range(len(rebalance_dates) - 1):
            start = rebalance_dates[i]
            end = rebalance_dates[i + 1]
            picks = self.picks_for_date(close_series, start)
            latest_picks = picks

            if not picks:
                portfolio_values.append(portfolio_values[-1])
                continue

            returns: list[float] = []
            for pick in picks:
                series = close_series[pick.symbol]
                start_point = self._value_on_or_before(series, start)
                end_point = self._value_on_or_before(series, end)
                if start_point is None or end_point is None:
                    continue

                start_close = start_point[1]
                end_close = end_point[1]
                if start_close <= 0:
                    continue
                r = (end_close / start_close) - 1
                returns.append(r)

                selection_return_by_symbol[pick.symbol] = (
                    (1 + selection_return_by_symbol.get(pick.symbol, 0.0)) * (1 + r)
                ) - 1

            if returns:
                period_return = sum(returns) / len(returns)
                portfolio_values.append(portfolio_values[-1] * (1 + period_return))
            else:
                portfolio_values.append(portfolio_values[-1])

        return QualitySimulationResult(
            rebalance_dates=rebalance_dates,
            portfolio_values=portfolio_values,
            latest_picks=latest_picks,
            selection_return_by_symbol=selection_return_by_symbol,
        )


class ScannerPipeline:
    def __init__(self, db: Database, client: YFinanceClient) -> None:
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

    def run_quality_simulation(
        self,
        symbols: list[str],
        period: str = "3y",
        lookback_days: int = 90,
        threshold: float = 0.15,
        top_n: int = 10,
    ) -> QualitySimulationResult:
        close_series: dict[str, list[tuple[date, float]]] = {}
        for symbol in symbols:
            bars = self.client.get_historical_bars(symbol=symbol, period=period)
            series: list[tuple[date, float]] = []
            for bar in bars:
                series.append((date.fromisoformat(bar.trade_date), bar.close))
            if series:
                close_series[symbol] = series

        strategy = QualityStrategy(lookback_days=lookback_days, threshold=threshold, top_n=top_n)
        return strategy.simulate(close_series)
