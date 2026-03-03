import pytest

from scanner.rate_limiter import CompositeRateLimiter, RateLimitExceeded


def test_daily_limit_reached() -> None:
    limiter = CompositeRateLimiter(calls_per_minute=100, calls_per_day=2)
    limiter.acquire()
    limiter.acquire()

    with pytest.raises(RateLimitExceeded):
        limiter.acquire()
