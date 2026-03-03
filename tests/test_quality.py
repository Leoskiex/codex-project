from datetime import date, timedelta

from scanner.main import parse_symbols_csv
from scanner.pipeline import QualityStrategy


def _series(start: date, days: int, daily_growth: float, base: float = 100.0) -> list[tuple[date, float]]:
    out: list[tuple[date, float]] = []
    px = base
    d = start
    while len(out) < days:
        if d.weekday() < 5:
            px *= 1 + daily_growth
            out.append((d, px))
        d += timedelta(days=1)
    return out


def test_parse_symbols_csv_dedupes_and_uppercases() -> None:
    assert parse_symbols_csv(" nvda,MSFT,nvda, aapl ") == ["NVDA", "MSFT", "AAPL"]


def test_quality_strategy_picks_only_above_threshold() -> None:
    strategy = QualityStrategy(lookback_days=90, threshold=0.15, top_n=10)
    closes = {
        "FAST": _series(date(2024, 1, 1), 220, daily_growth=0.003),
        "SLOW": _series(date(2024, 1, 1), 220, daily_growth=0.0005),
    }
    picks = strategy.picks_for_date(closes, closes["FAST"][-1][0])

    assert picks
    assert picks[0].symbol == "FAST"
    assert all(p.symbol != "SLOW" for p in picks)


def test_quality_strategy_simulation_reports_best_selected_stock() -> None:
    strategy = QualityStrategy(lookback_days=90, threshold=0.15, top_n=2)
    closes = {
        "META": _series(date(2024, 1, 1), 260, daily_growth=0.0025),
        "NVDA": _series(date(2024, 1, 1), 260, daily_growth=0.0018),
        "AAPL": _series(date(2024, 1, 1), 260, daily_growth=0.0002),
    }
    result = strategy.simulate(closes)

    assert len(result.rebalance_dates) > 3
    assert result.portfolio_values[-1] > 1.0
    assert "META" in result.selection_return_by_symbol
    assert result.selection_return_by_symbol["META"] >= result.selection_return_by_symbol.get("NVDA", 0.0)


def test_quality_strategy_spectrum_classifies_increasing_and_dropping() -> None:
    strategy = QualityStrategy(lookback_days=90, threshold=0.15, top_n=2)
    inc_series: list[tuple[date, float]] = []
    px = 100.0
    d = date(2024, 1, 1)
    while len(inc_series) < 260:
        if d.weekday() < 5:
            growth = 0.0
            if len(inc_series) > 200:
                growth = 0.01
            elif len(inc_series) > 150:
                growth = 0.004
            px *= 1 + growth
            inc_series.append((d, px))
        d += timedelta(days=1)

    closes = {
        "INC": inc_series,
        "DROP": _series(date(2024, 1, 1), 260, daily_growth=0.0001),
    }
    # Force DROP to have weaker recent returns vs older window.
    adjusted = []
    for i, (d, c) in enumerate(closes["DROP"]):
        if i > 220:
            adjusted.append((d, c * 0.995))
        else:
            adjusted.append((d, c))
    closes["DROP"] = adjusted

    rows = strategy.momentum_spectrum_for_date(closes, closes["INC"][-1][0])
    states = {r.symbol: r.trend_state for r in rows}
    inc_row = next(r for r in rows if r.symbol == "INC")

    assert inc_row.m7 > 0
    assert inc_row.m90 > 0
    assert states["DROP"] in {"Dropping Off", "Mixed"}
