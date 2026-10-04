"""简单线程安全 TTL 缓存(进程内)"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class _Entry(Generic[V]):
    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    """进程内 TTL 缓存，适合减少重复外部调用的开销。"""

    def __init__(self, default_ttl_seconds: float = 60.0, max_size: int = 512):
        self._default_ttl = float(default_ttl_seconds)
        self._max_size = int(max_size)
        self._lock = threading.Lock()
        self._data: dict[K, _Entry[V]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def get(self, key: K) -> Optional[V]:
        now = self._now()
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if entry.expires_at <= now:
                self._data.pop(key, None)
                return None
            return entry.value

    def set(self, key: K, value: V, ttl_seconds: Optional[float] = None) -> None:
        ttl = self._default_ttl if ttl_seconds is None else float(ttl_seconds)
        expires_at = self._now() + ttl
        with self._lock:
            if len(self._data) >= self._max_size:
                # 简单清理: 先清理过期; 仍超限则弹出最早插入的一个
                self._purge_expired_locked()
                if len(self._data) >= self._max_size:
                    try:
                        oldest_key = next(iter(self._data.keys()))
                        self._data.pop(oldest_key, None)
                    except StopIteration:
                        pass
            self._data[key] = _Entry(value=value, expires_at=expires_at)

    def get_or_set(self, key: K, factory: Callable[[], V], ttl_seconds: Optional[float] = None) -> V:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    def _purge_expired_locked(self) -> None:
        now = self._now()
        expired_keys = [k for k, v in self._data.items() if v.expires_at <= now]
        for k in expired_keys:
            self._data.pop(k, None)

