from __future__ import annotations

import json
import tempfile
from pathlib import Path
from threading import Lock
from time import time
from typing import Any

CACHE_DIR = Path(tempfile.gettempdir()) / "fftt_top3_web_cache"
CACHE_FILE = CACHE_DIR / "cache.json"
CACHE_LOCK = Lock()


def _ensure_storage() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not CACHE_FILE.exists():
        CACHE_FILE.write_text("{}", encoding="utf-8")


def _read_cache() -> dict[str, Any]:
    _ensure_storage()
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_cache(payload: dict[str, Any]) -> None:
    _ensure_storage()
    temp_file = CACHE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(CACHE_FILE)


def get_cache(key: str, max_age_seconds: int | None = None) -> dict[str, Any] | None:
    with CACHE_LOCK:
        cache = _read_cache()
        item = cache.get(key)
        if not item:
            return None

        if max_age_seconds is not None:
            age = time() - float(item.get("timestamp", 0))
            if age > max_age_seconds:
                return None

        return item.get("value")


def set_cache(key: str, value: Any) -> None:
    with CACHE_LOCK:
        cache = _read_cache()
        cache[key] = {"timestamp": time(), "value": value}
        _write_cache(cache)


def clear_cache(key: str | None = None) -> None:
    with CACHE_LOCK:
        if key is None:
            _write_cache({})
            return

        cache = _read_cache()
        if key in cache:
            del cache[key]
            _write_cache(cache)
