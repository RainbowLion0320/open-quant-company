"""Shared fetcher infrastructure for external data providers."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from core.settings import get_tushare_token


@dataclass(frozen=True)
class RateLimiter:
    """Simple synchronous limiter for low-frequency provider calls."""

    base_seconds: float = 1.5
    jitter_seconds: float = 1.0

    def sleep(self) -> None:
        jitter = random.uniform(0, self.jitter_seconds) if self.jitter_seconds > 0 else 0.0
        time.sleep(max(0.0, self.base_seconds + jitter))


DEFAULT_AKSHARE_LIMITER = RateLimiter(base_seconds=1.5, jitter_seconds=1.0)


def throttle(limiter: RateLimiter = DEFAULT_AKSHARE_LIMITER) -> None:
    """Sleep before a provider request."""
    limiter.sleep()


__all__ = ["DEFAULT_AKSHARE_LIMITER", "RateLimiter", "get_tushare_token", "throttle"]
