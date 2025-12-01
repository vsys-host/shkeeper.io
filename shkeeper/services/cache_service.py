import time
from typing import Callable, Any

class TTLCache:
    def __init__(self):
        self._cache = {}

    def remember(self, key: str, ttl: int, callback: Callable[[], Any]):
        entry = self._cache.get(key)
        if entry and entry["expires"] > time.time():
            return entry["value"]
        value = callback()
        self._cache[key] = {
            "value": value,
            "expires": time.time() + ttl
        }
        return value
cache = TTLCache()
