from __future__ import annotations

import argparse
import csv
from datetime import date

from scanner.config import load_settings
from scanner.db import Database
from scanner.fugle_client import YFinanceClient
from scanner.pipeline import MomentumSpectrumRow, QualityStrategy, ScannerPipeline


def read_symbols_file(path: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            symbol = line.strip()
            if not symbol or symbol.startswith("#"):
                continue
            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    return symbols


def parse_symbols_csv(raw: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for token in raw.split(","):
        symbol = token.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def load_close_series_csv(path: str, symbols: list[str]) -> dict[str, list[tuple[date, float]]]:
    allowed = set(symbols)
    close_series: dict[str, list[tuple[date, float]]] = {s: [] for s in symbols}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row["symbol"].strip().upper()
            if symbol not in allowed:
                continue
            close_series[symbol].append((date.fromisoformat(row["trade_date"]), float(row["close"])))

    for symbol in symbols:
        close_series[symbol].sort(key=lambda item: item[0])

    return {k: v for k, v in close_series.items() if v}


def build_pipeline() -> tuple[ScannerPipeline, tuple[str, ...]]:
    settings = load_settings()
    db = Database(settings.db_path)
    client = YFinanceClient()
    return ScannerPipeline(db=db, client=client), settings.top_symbols


def cmd_init_db() -> None:
    settings = load_settings()
    db = Database(settings.db_path)
    db.init_schema()
    db.close()
    print("Schema initialized")


def cmd_bootstrap(symbols_file: str | None, batch_size: int, offset: int) -> None:
    pipeline, top_symbols = build_pipeline()
    pipeline.db.init_schema()

    symbols = read_symbols_file(symbols_file) if symbols_file else list(top_symbols)
    selected = symbols[offset : offset + batch_size]
    updated = pipeline.bootstrap_batch(symbols=selected, batch_size=len(selected))
    pipeline.db.close()
    print(f"Bootstrap complete: updated {updated} symbols (offset={offset}, batch_size={len(selected)})")


def cmd_daily_scan(top_liquidity: int, top_candidates: int, symbols_file: str | None) -> None:
    pipeline, top_symbols = build_pipeline()
    pipeline.db.init_schema()

    symbols = read_symbols_file(symbols_file) if symbols_file else list(top_symbols)

    try:
        refreshed = pipeline.refresh_latest_bars(symbols)
        latest_trade_date = pipeline.db.latest_trade_date()
        target_date = date.fromisoformat(latest_trade_date) if latest_trade_date else date.today()
        candidates = pipeline.run_daily_scan(top_liquidity, top_candidates, target_date=target_date)
    finally:
        pipeline.db.close()

    print(f"Refreshed latest bars: {refreshed}")
    print(f"Scan date: {target_date.isoformat()}")
    print("symbol\ttotal_score\tv2\tv3\tpivot_bonus\tstatus")
    for c in candidates:
        print(
            f"{c.symbol}\t{c.total_score:.2f}\t{c.score_v2:.2f}\t"
            f"{c.score_v3:.2f}\t{c.pivot_bonus:.2f}\t{c.status}"
        )


def cmd_quality_sim(
    symbols_raw: str,
    lookback_days: int,
    threshold: float,
    top_n: int,
    period: str,
    prices_file: str | None,
) -> None:
    symbols = parse_symbols_csv(symbols_raw)
    if not symbols:
        raise ValueError("No symbols provided to quality-sim")

    if prices_file:
        close_series = load_close_series_csv(prices_file, symbols)
        strategy = QualityStrategy(lookback_days=lookback_days, threshold=threshold, top_n=top_n)
        result = strategy.simulate(close_series)
    else:
        pipeline, _ = build_pipeline()
        try:
            result = pipeline.run_quality_simulation(
                symbols=symbols,
                period=period,
                lookback_days=lookback_days,
                threshold=threshold,
                top_n=top_n,
            )
        finally:
            pipeline.db.close()

    if not result.rebalance_dates:
        print("No enough data for simulation.")
        return

    start = result.portfolio_values[0]
    end = result.portfolio_values[-1]
    total_return = (end / start) - 1 if start > 0 else 0.0

    print(f"Quality simulation window: {result.rebalance_dates[0]} -> {result.rebalance_dates[-1]}")
    print(f"Portfolio total return: {total_return:.2%}")
    print("Latest monthly picks (symbol, momentum_90d):")
    for pick in result.latest_picks:
        print(f"- {pick.symbol}: {pick.momentum_90d:.2%}")

    if result.selection_return_by_symbol:
        best_symbol = max(result.selection_return_by_symbol, key=result.selection_return_by_symbol.get)
        print(
            "Best selected performer: "
            f"{best_symbol} ({result.selection_return_by_symbol[best_symbol]:.2%} cumulative while selected)"
        )


def cmd_quality_pipeline(
    symbols_file: str,
    prices_file: str,
    top_core: int,
    top_quality: int,
    lookback_days: int,
    threshold: float,
) -> None:
    symbols = read_symbols_file(symbols_file)
    if not symbols:
        raise ValueError("symbols-file is empty")

    core_basket = symbols[:top_core]
    close_series = load_close_series_csv(prices_file, symbols)
    if not close_series:
        print("No matching close data found for supplied symbols.")
        return

    latest_date = max(series[-1][0] for series in close_series.values())
    strategy = QualityStrategy(lookback_days=lookback_days, threshold=threshold, top_n=top_quality)
    picks = strategy.picks_for_date(close_series, latest_date)
    spectrum = strategy.momentum_spectrum_for_date(close_series, latest_date)
    spectrum_map: dict[str, MomentumSpectrumRow] = {row.symbol: row for row in spectrum}

    print(f"Pipeline date: {latest_date}")
    print(f"Core basket (top {top_core}):")
    print(", ".join(core_basket))
    print("")
    print(f"Quality picks (top {top_quality}, 90d>{threshold:.0%}):")
    print("symbol\tm90\tstate\tm7\tm14\tm21\tm30\tm60")
    for pick in picks:
        row = spectrum_map.get(pick.symbol)
        if not row:
            continue
        print(
            f"{row.symbol}\t{row.m90:.2%}\t{row.trend_state}\t{row.m7:.2%}\t{row.m14:.2%}\t"
            f"{row.m21:.2%}\t{row.m30:.2%}\t{row.m60:.2%}"
        )

    print("")
    print("Top 30 momentum spectrum:")
    print("symbol\tm90\tstate\tm7\tm14\tm21\tm30\tm60")
    for row in spectrum[:30]:
        print(
            f"{row.symbol}\t{row.m90:.2%}\t{row.trend_state}\t{row.m7:.2%}\t{row.m14:.2%}\t"
            f"{row.m21:.2%}\t{row.m30:.2%}\t{row.m60:.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="YFinance top-stock scanner")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    p_bootstrap = sub.add_parser("bootstrap")
    p_bootstrap.add_argument("--symbols-file")
    p_bootstrap.add_argument("--batch-size", type=int, default=20)
    p_bootstrap.add_argument("--offset", type=int, default=0)

    p_daily = sub.add_parser("daily-scan")
    p_daily.add_argument("--top-liquidity", type=int, default=20)
    p_daily.add_argument("--top-candidates", type=int, default=10)
    p_daily.add_argument("--symbols-file")

    p_quality = sub.add_parser("quality-sim")
    p_quality.add_argument(
        "--symbols",
        default="NVDA,AAPL,MSFT,GOOGL,META,AMZN,AMD",
        help="comma-separated symbols",
    )
    p_quality.add_argument("--lookback-days", type=int, default=90)
    p_quality.add_argument("--threshold", type=float, default=0.15)
    p_quality.add_argument("--top-n", type=int, default=10)
    p_quality.add_argument("--period", default="3y")
    p_quality.add_argument(
        "--prices-file",
        help="optional offline CSV with columns: symbol,trade_date,close",
    )

    p_quality_pipeline = sub.add_parser("quality-pipeline")
    p_quality_pipeline.add_argument("--symbols-file", required=True)
    p_quality_pipeline.add_argument("--prices-file", required=True)
    p_quality_pipeline.add_argument("--top-core", type=int, default=20)
    p_quality_pipeline.add_argument("--top-quality", type=int, default=20)
    p_quality_pipeline.add_argument("--lookback-days", type=int, default=90)
    p_quality_pipeline.add_argument("--threshold", type=float, default=0.15)

    args = parser.parse_args()

    if args.command == "init-db":
        cmd_init_db()
    elif args.command == "bootstrap":
        cmd_bootstrap(symbols_file=args.symbols_file, batch_size=args.batch_size, offset=args.offset)
    elif args.command == "daily-scan":
        cmd_daily_scan(
            top_liquidity=args.top_liquidity,
            top_candidates=args.top_candidates,
            symbols_file=args.symbols_file,
        )
    elif args.command == "quality-sim":
        cmd_quality_sim(
            symbols_raw=args.symbols,
            lookback_days=args.lookback_days,
            threshold=args.threshold,
            top_n=args.top_n,
            period=args.period,
            prices_file=args.prices_file,
        )
    elif args.command == "quality-pipeline":
        cmd_quality_pipeline(
            symbols_file=args.symbols_file,
            prices_file=args.prices_file,
            top_core=args.top_core,
            top_quality=args.top_quality,
            lookback_days=args.lookback_days,
            threshold=args.threshold,
        )


if __name__ == "__main__":
    main()
