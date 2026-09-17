"""Bounded, thread-safe storage for disposable in-process response caches."""
from collections import OrderedDict
from collections.abc import Iterator, MutableMapping
from threading import RLock
from time import monotonic
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(MutableMapping[str, T], Generic[T]):
    def __init__(self, max_entries: int = 64, ttl: float = 300):
        self.max_entries = max_entries
        self.ttl = ttl
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = RLock()

    def _expire(self) -> None:
        cutoff = monotonic() - self.ttl
        while self._data and next(iter(self._data.values()))[0] <= cutoff:
            self._data.popitem(last=False)

    def __getitem__(self, key: str) -> T:
        with self._lock:
            self._expire()
            return self._data[key][1]

    def __setitem__(self, key: str, value: T) -> None:
        with self._lock:
            self._expire()
            self._data.pop(key, None)
            self._data[key] = (monotonic(), value)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def __delitem__(self, key: str) -> None:
        with self._lock:
            del self._data[key]

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            self._expire()
            return iter(list(self._data))

    def __len__(self) -> int:
        with self._lock:
            self._expire()
            return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
