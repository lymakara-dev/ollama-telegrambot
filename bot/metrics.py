from collections import Counter
from threading import Lock
from typing import Any, Dict


class BotMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counter = Counter()

    def inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counter[key] += amount

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._counter)
