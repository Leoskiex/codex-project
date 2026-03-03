from scanner.db import DailyBar
from scanner.pipeline import StrategyEngine


def _bar(idx: int, open_: float, high: float, low: float, close: float, volume: float) -> DailyBar:
    return DailyBar(
        symbol="2330",
        trade_date=f"2026-01-{idx:02d}",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        turnover=volume * close,
    )


def test_strategy_marks_strong_candidate_for_v3_plus_pivot():
    bars = []

    bars.append(_bar(60, 159, 166, 120, 165, 3000))
    bars.append(_bar(59, 158, 160, 150, 155, 1800))

    for idx in range(58, 30, -1):
        base = 130 + (58 - idx)
        bars.append(_bar(idx, base, base + 2, base - 2, base + 1, 1500))

    for idx in range(30, 0, -1):
        base = 90 + (30 - idx) * 0.2
        bars.append(_bar(idx, base, base + 1, base - 1, base, 1200))

    total, v2, v3, pivot, status = StrategyEngine().score(bars[:60])

    assert v2 == 30
    assert v3 >= 50
    assert pivot >= 5
    assert total >= 70
    assert status == "Strong Candidate"


def test_strategy_v3_bonuses_not_applied_without_core_breakout():
    bars = []
    bars.append(_bar(60, 120, 122, 118, 121, 2000))  # no breakout
    bars.append(_bar(59, 118, 121, 116, 119, 1500))

    for idx in range(58, 0, -1):
        base = 100 + (58 - idx) * 0.4
        bars.append(_bar(idx, base, base + 3, base - 1, base + 2, 1300))

    _, _, v3, _, _ = StrategyEngine().score(bars[:60])
    assert v3 == 0


def test_strategy_returns_zero_for_insufficient_bars():
    bars = [_bar(i + 1, 100, 101, 99, 100, 1000) for i in range(10)]
    total, v2, v3, pivot, status = StrategyEngine().score(bars)

    assert total == 0
    assert v2 == 0
    assert v3 == 0
    assert pivot == 0
    assert status == "Watch Only"
