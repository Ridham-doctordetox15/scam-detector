"""Simple in-memory sliding-window rate limiter, per client and per endpoint bucket.

Good enough for a single-process free-tier deployment: state lives in this
process only (lost on restart, not shared between workers - the app runs one
worker). Client addresses are held in memory only, never logged, and the
number of tracked clients is bounded so memory can't grow without limit.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Callable, Mapping


class RateLimiter:
    """Allow at most ``limits[bucket]`` requests per ``window_s`` per client.

    Args:
        limits: Requests allowed per window, per bucket name. ``0`` disables
            limiting for that bucket.
        window_s: Window length in seconds.
        clock: Monotonic clock (injectable for tests).
        max_clients: Tracked (bucket, client) keys; the least recently seen are evicted.
    """

    def __init__(
        self,
        limits: Mapping[str, int],
        window_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_clients: int = 10_000,
    ) -> None:
        self.limits = dict(limits)
        self.window_s = window_s
        self.clock = clock
        self.max_clients = max_clients
        self._hits: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, bucket: str, client: str) -> float | None:
        """Record a request. Returns ``None`` if allowed, else seconds until the next slot frees."""
        limit = self.limits.get(bucket, 0)
        if limit <= 0:
            return None
        now = self.clock()
        key = (bucket, client)
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
                while len(self._hits) > self.max_clients:
                    self._hits.popitem(last=False)
            else:
                self._hits.move_to_end(key)
            while hits and hits[0] <= now - self.window_s:
                hits.popleft()
            if len(hits) >= limit:
                return max(0.0, hits[0] + self.window_s - now)
            hits.append(now)
            return None

    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._hits)


def client_key(peer_host: str | None, forwarded_for: str | None, trusted_proxy_hops: int) -> str:
    """The client address used for rate limiting.

    Behind ``trusted_proxy_hops`` reverse proxies, each proxy appends the
    address it received the request from to ``X-Forwarded-For``, so the real
    client is the entry that many positions from the end. Entries further
    left were supplied by the client and can be spoofed, so they are ignored.
    """
    if trusted_proxy_hops > 0 and forwarded_for:
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        if len(parts) >= trusted_proxy_hops:
            return parts[-trusted_proxy_hops]
    return peer_host or "unknown"
