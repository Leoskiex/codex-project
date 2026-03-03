from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TOP_SYMBOLS = [
    "2330.TW",  # 台積電
    "2317.TW",  # 鴻海
    "2454.TW",  # 聯發科
    "2308.TW",  # 台達電
    "2412.TW",  # 中華電
    "2881.TW",  # 富邦金
    "2882.TW",  # 國泰金
    "2891.TW",  # 中信金
    "2886.TW",  # 兆豐金
    "1301.TW",  # 台塑
    "1303.TW",  # 南亞
    "2002.TW",  # 中鋼
    "2303.TW",  # 聯電
    "3711.TW",  # 日月光投控
    "2382.TW",  # 廣達
    "2603.TW",  # 長榮
    "2615.TW",  # 萬海
    "2609.TW",  # 陽明
    "3034.TW",  # 聯詠
    "2884.TW",  # 玉山金
]


@dataclass(frozen=True)
class Settings:
    db_path: str = "market.db"
    top_symbols: tuple[str, ...] = tuple(DEFAULT_TOP_SYMBOLS)


def _parse_top_symbols(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return tuple(DEFAULT_TOP_SYMBOLS)

    symbols: list[str] = []
    seen: set[str] = set()
    for token in raw.split(","):
        symbol = token.strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return tuple(symbols) if symbols else tuple(DEFAULT_TOP_SYMBOLS)


def load_settings() -> Settings:
    return Settings(
        db_path=os.getenv("SCANNER_DB_PATH", "market.db"),
        top_symbols=_parse_top_symbols(os.getenv("TOP_SYMBOLS", "")),
    )
