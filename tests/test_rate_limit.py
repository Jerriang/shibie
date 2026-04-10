from app.services.rate_limit import SlidingWindowRateLimiter


def test_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowRateLimiter(limit_per_minute=2)
    assert limiter.allow("d1") is True
    assert limiter.allow("d1") is True
    assert limiter.allow("d1") is False


def test_rate_limiter_isolated_by_key():
    limiter = SlidingWindowRateLimiter(limit_per_minute=1)
    assert limiter.allow("d1") is True
    assert limiter.allow("d2") is True
