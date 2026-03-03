from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://api.fugle.tw"
    db_path: str = "market.db"
    calls_per_day: int = 500
    calls_per_minute: int = 60


def load_settings(require_api_key: bool = True) -> Settings:
    api_key = os.getenv("FUGLE_API_KEY", "")
    if require_api_key and not api_key:
        raise ValueError("FUGLE_API_KEY is required")

    return Settings(
        api_key=api_key,
        base_url=os.getenv("FUGLE_BASE_URL", "https://api.fugle.tw"),
        db_path=os.getenv("SCANNER_DB_PATH", "market.db"),
        calls_per_day=int(os.getenv("CALLS_PER_DAY", "500")),
        calls_per_minute=int(os.getenv("CALLS_PER_MIN", "60")),
    )
