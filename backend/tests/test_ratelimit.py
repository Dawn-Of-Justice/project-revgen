"""The spend guard.

Pure and clock-injected, so none of this sleeps or touches the network.
"""

from __future__ import annotations

from app.ratelimit import Limiter


def test_normal_use_is_never_limited():
    """50 commands spread over a day, which is what she will actually do."""
    lim = Limiter(per_minute=20, per_day=200)
    now = 1000.0
    for _ in range(50):
        assert lim.check(now).allowed
        now += 300          # one command every five minutes
    assert lim.stats["today"] == 50


def test_burst_is_stopped_at_the_minute_cap():
    lim = Limiter(per_minute=20, per_day=200)
    now = 1000.0
    allowed = sum(lim.check(now + i * 0.1).allowed for i in range(100))
    assert allowed == 20


def test_retry_loop_cannot_run_up_a_bill_overnight():
    """A wedged client hammering every 100ms for 8 hours.

    Without the guard that is ~288,000 requests. The point of this test is the
    number on the right: whatever the client does, the bill is bounded.
    """
    lim = Limiter(per_minute=20, per_day=200)
    now = 1000.0
    allowed = 0
    for i in range(288_000):
        if lim.check(now + i * 0.1).allowed:
            allowed += 1
    assert allowed == 200, "daily cap is the backstop and must hold"


def test_minute_window_rolls_forward():
    lim = Limiter(per_minute=5, per_day=200)
    for i in range(5):
        assert lim.check(1000.0 + i).allowed
    assert not lim.check(1005.0).allowed
    # once the first request is more than 60s old, capacity returns
    assert lim.check(1061.0).allowed


def test_daily_counter_resets_after_24h():
    lim = Limiter(per_minute=1000, per_day=3)
    for i in range(3):
        assert lim.check(1000.0 + i).allowed
    assert not lim.check(1004.0).allowed
    assert lim.check(1000.0 + 86_401).allowed


def test_verdict_explains_which_limit_and_when_to_retry():
    lim = Limiter(per_minute=2, per_day=100)
    lim.check(1000.0)
    lim.check(1000.5)
    v = lim.check(1001.0)
    assert not v.allowed
    assert v.reason == "minute"
    assert 1 <= v.retry_after_s <= 60


def test_blocked_requests_are_not_counted_against_the_day():
    """Otherwise a loop would burn the daily budget while being refused."""
    lim = Limiter(per_minute=2, per_day=100)
    for i in range(50):
        lim.check(1000.0 + i * 0.01)
    assert lim.stats["today"] == 2
