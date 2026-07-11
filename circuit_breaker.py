"""
circuit_breaker.py — the breaker logic lifted out of module globals into
a reusable class. Same state machine already tested in waking_loop
(CLOSED -> OPEN -> HALF_OPEN, exponential cooldown), just not tied to
Ollama specifically anymore. Any function that can fail gets wrapped
the same way: corpus loads, future API calls, anything.

Single interface: breaker.execute(fn, *args, **kwargs). Callers don't
touch state directly -- that's what "single interface" means here, and
it's the thing that keeps this from sprawling into ad hoc per-caller
breaker logic the way the globals version could have.
"""

from datetime import datetime
from typing import Callable, Any


class BreakerOpenError(Exception):
    """Raised by execute() when the call is blocked. Callers catch this
    instead of checking state themselves."""
    def __init__(self, state: str, cooldown_remaining_min: float):
        self.state = state
        self.cooldown_remaining_min = cooldown_remaining_min
        super().__init__(f"Breaker {state}, {cooldown_remaining_min:.1f} min remaining")


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3,
                 base_cooldown_minutes: float = 5,
                 max_cooldown_minutes: float = 60,
                 name: str = "breaker"):
        self.failure_threshold = failure_threshold
        self.base_cooldown_minutes = base_cooldown_minutes
        self.max_cooldown_minutes = max_cooldown_minutes
        self.name = name

        self._state = "CLOSED"
        self._failure_count = 0
        self._tripped_at = None
        self._consecutive_trips = 0

    @property
    def state(self) -> str:
        return self._state

    def _current_cooldown(self) -> float:
        return min(
            self.base_cooldown_minutes * (2 ** max(self._consecutive_trips - 1, 0)),
            self.max_cooldown_minutes,
        )

    def _allows_call(self) -> bool:
        if self._state == "CLOSED":
            return True
        if self._state == "OPEN":
            elapsed = (datetime.now() - self._tripped_at).total_seconds() / 60
            if elapsed >= self._current_cooldown():
                self._state = "HALF_OPEN"
                return True
            return False
        return False  # HALF_OPEN: a probe is already in flight

    def _record_success(self):
        self._state = "CLOSED"
        self._failure_count = 0
        self._consecutive_trips = 0

    def _record_failure(self):
        if self._state == "HALF_OPEN":
            self._consecutive_trips += 1
            self._state = "OPEN"
            self._tripped_at = datetime.now()
            return
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold and self._state == "CLOSED":
            self._consecutive_trips = 1
            self._state = "OPEN"
            self._tripped_at = datetime.now()

    def execute(self, fn: Callable, *args, **kwargs) -> Any:
        """Run fn(*args, **kwargs) through the breaker. Raises
        BreakerOpenError if blocked; re-raises whatever fn raises on
        failure, after recording it. Success is whatever fn returns."""
        if not self._allows_call():
            elapsed = (datetime.now() - self._tripped_at).total_seconds() / 60
            remaining = max(self._current_cooldown() - elapsed, 0)
            raise BreakerOpenError(self._state, remaining)
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result


if __name__ == "__main__":
    # Same four transitions verified for the globals version, now against
    # the class, to confirm the lift-and-drop didn't change behavior.
    from datetime import timedelta

    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        raise ConnectionError("down")

    def works():
        return "ok"

    cb = CircuitBreaker(failure_threshold=3, base_cooldown_minutes=5)

    print("--- trip after 3 failures ---")
    for i in range(3):
        try:
            cb.execute(flaky)
        except ConnectionError:
            print(f"call {i}: failed normally, state={cb.state}")
    assert cb.state == "OPEN"

    print("--- blocked call raises BreakerOpenError, fn never invoked ---")
    calls_before = calls["count"]
    try:
        cb.execute(flaky)
    except BreakerOpenError as e:
        print(f"blocked as expected: {e}")
    assert calls["count"] == calls_before, "fn should not have been called"

    print("--- fast-forward past cooldown, probe fails -> reopen longer ---")
    cb._tripped_at = datetime.now() - timedelta(minutes=6)
    try:
        cb.execute(flaky)
    except ConnectionError:
        pass
    print(f"state={cb.state}, consecutive_trips={cb._consecutive_trips}, "
          f"cooldown={cb._current_cooldown()} min")
    assert cb.state == "OPEN" and cb._current_cooldown() == 10

    print("--- fast-forward again, probe succeeds -> full reset ---")
    cb._tripped_at = datetime.now() - timedelta(minutes=15)
    result = cb.execute(works)
    print(f"result={result}, state={cb.state}")
    assert cb.state == "CLOSED" and cb._consecutive_trips == 0

    print("\nALL TRANSITIONS CONFIRMED — behavior matches the globals version")
