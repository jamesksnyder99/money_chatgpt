from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def _code_name(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if callable(code):
        try:
            value = code()
            return getattr(value, "name", "") or str(value)
        except Exception:  # noqa: BLE001
            return ""
    return ""


def is_rate_limit(exc: BaseException) -> bool:
    name = _code_name(exc).upper()
    msg = str(exc).lower()
    return (
        name in {"RESOURCE_EXHAUSTED", "ABORTED"}
        or "429" in msg
        or "too many concurrent" in msg
        or "resource_exhausted" in msg
    )


def is_retryable(exc: BaseException) -> bool:
    if is_rate_limit(exc):
        return True
    name = _code_name(exc).upper()
    msg = str(exc).lower()
    return name in {"UNAVAILABLE", "DEADLINE_EXCEEDED", "INTERNAL"} or "timeout" in msg


class ThetaLimiter:
    def __init__(self, concurrency: int) -> None:
        self._lock = threading.Condition()
        self._limit = max(1, int(concurrency))
        self._active = 0

    @property
    def concurrency(self) -> int:
        with self._lock:
            return self._limit

    def acquire(self) -> None:
        with self._lock:
            while self._active >= self._limit:
                self._lock.wait()
            self._active += 1

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
            self._lock.notify()

    def halve(self) -> int:
        with self._lock:
            self._limit = max(1, self._limit // 2)
            self._lock.notify_all()
            return self._limit


def call_theta(limiter: ThetaLimiter, fn: Callable[..., T], *args, **kwargs) -> tuple[T, float]:
    delays = (0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0)
    last: BaseException | None = None
    for i, delay in enumerate(delays):
        if delay:
            time.sleep(delay)
        limiter.acquire()
        t0 = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            return result, time.perf_counter() - t0
        except Exception as exc:  # noqa: BLE001
            last = exc
            if is_rate_limit(exc):
                new_n = limiter.halve()
                print(f"theta backoff: {type(exc).__name__}; concurrency now {new_n}")
            elif not is_retryable(exc) or i == len(delays) - 1:
                raise
        finally:
            limiter.release()
    assert last is not None
    raise last
