from __future__ import annotations

from app import refresh_all_cache


def build_refresh_payload() -> dict[str, object]:
    return refresh_all_cache()
