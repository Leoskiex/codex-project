from __future__ import annotations

import argparse
from datetime import date

from scanner.config import load_settings
from scanner.db import Database
from scanner.fugle_client import FugleClient
from scanner.pipeline import ScannerPipeline
from scanner.rate_limiter import CompositeRateLimiter, RateLimitExceeded


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


def build_pipeline() -> ScannerPipeline:
    settings = load_settings()
    db = Database(settings.db_path)
    limiter = CompositeRateLimiter(settings.calls_per_minute, settings.calls_per_day)
    client = FugleClient(settings.api_key, settings.base_url, limiter)
    return ScannerPipeline(db=db, client=client)


def cmd_init_db() -> None:
    settings = load_settings(require_api_key=False)
    db = Database(settings.db_path)
    db.init_schema()
    db.close()
    print("Schema initialized")


def cmd_bootstrap(symbols_file: str, batch_size: int, offset: int) -> None:
    pipeline = build_pipeline()
    pipeline.db.init_schema()

    symbols = read_symbols_file(symbols_file)
    selected = symbols[offset : offset + batch_size]
    updated = pipeline.bootstrap_batch(symbols=selected, batch_size=len(selected))
    pipeline.db.close()
    print(f"Bootstrap complete: updated {updated} symbols (offset={offset}, batch_size={len(selected)})")


def cmd_daily_scan(top_liquidity: int, top_candidates: int) -> None:
    pipeline = build_pipeline()
    pipeline.db.init_schema()

    today = date.today()

    try:
        symbols = pipeline.db.get_symbols_missing_latest(max_count=top_liquidity, target_date=today)
        refreshed = pipeline.refresh_latest_bars(symbols)
        candidates = pipeline.run_daily_scan(top_liquidity, top_candidates, target_date=today)
    except RateLimitExceeded as exc:
        print(f"Rate limit exceeded: {exc}")
        return
    finally:
        pipeline.db.close()

    print(f"Refreshed latest bars: {refreshed}")
    print("symbol\ttotal_score\tv2\tv3\tpivot_bonus\tstatus")
    for c in candidates:
        print(
            f"{c.symbol}\t{c.total_score:.2f}\t{c.score_v2:.2f}\t"
            f"{c.score_v3:.2f}\t{c.pivot_bonus:.2f}\t{c.status}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fugle layered scanner")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    p_bootstrap = sub.add_parser("bootstrap")
    p_bootstrap.add_argument("--symbols-file", required=True)
    p_bootstrap.add_argument("--batch-size", type=int, default=500)
    p_bootstrap.add_argument("--offset", type=int, default=0)

    p_daily = sub.add_parser("daily-scan")
    p_daily.add_argument("--top-liquidity", type=int, default=400)
    p_daily.add_argument("--top-candidates", type=int, default=50)

    args = parser.parse_args()

    if args.command == "init-db":
        cmd_init_db()
    elif args.command == "bootstrap":
        cmd_bootstrap(symbols_file=args.symbols_file, batch_size=args.batch_size, offset=args.offset)
    elif args.command == "daily-scan":
        cmd_daily_scan(top_liquidity=args.top_liquidity, top_candidates=args.top_candidates)


if __name__ == "__main__":
    main()
