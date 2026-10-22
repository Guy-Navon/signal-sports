"""In-memory rate-limiter state stays bounded (#200: "Limiter state is bounded
(TTL eviction), with a test that proves it").

Keys are attacker-supplied (a login email, a signup address), so a limiter
that never forgets grows without bound. Expired windows are evicted, and a
hard cap holds even while every key is still fresh. The per-key limit keeps
working for keys inside their window.
"""

from app.services.auth_service import FixedWindowLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_expired_windows_are_evicted():
    clock = Clock()
    limiter = FixedWindowLimiter(5, 60, max_keys=100, clock=clock)
    for i in range(50):
        limiter.check(f"user{i}@example.com")
    assert limiter.size() == 50
    clock.now += 61
    limiter.check("someone-new@example.com")
    assert limiter.size() == 1


def test_state_never_exceeds_the_cap_under_a_flood_of_fresh_keys():
    clock = Clock()
    limiter = FixedWindowLimiter(5, 60, max_keys=100, clock=clock)
    for i in range(10_000):
        limiter.check(f"flood{i}@example.com")
        assert limiter.size() <= 100
    assert limiter.size() <= 100


def test_a_key_inside_its_window_is_still_limited():
    clock = Clock()
    limiter = FixedWindowLimiter(2, 60, max_keys=100, clock=clock)
    assert limiter.check("victim@example.com")
    assert limiter.check("victim@example.com")
    for i in range(50):  # unrelated keys, under the cap
        limiter.check(f"other{i}@example.com")
    assert not limiter.check("victim@example.com")


def test_the_window_resets_after_it_expires():
    clock = Clock()
    limiter = FixedWindowLimiter(1, 60, max_keys=100, clock=clock)
    assert limiter.check("k")
    assert not limiter.check("k")
    clock.now += 60
    assert limiter.check("k")


def test_the_default_limiters_are_bounded():
    from app.services import auth_service, email_verification, google_oauth

    for limiter in (
        auth_service._account_login_limiter,
        auth_service._global_login_limiter,
        email_verification._signup_email_limiter,
        email_verification._global_send_limiter,
        email_verification._confirm_limiter,
        google_oauth._start_limiter,
    ):
        assert 0 < limiter.max_keys <= FixedWindowLimiter.DEFAULT_MAX_KEYS
