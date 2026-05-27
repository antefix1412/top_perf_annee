from __future__ import annotations

from app import refresh_all_cache


if __name__ == "__main__":
    payload = refresh_all_cache()
    print(f"Cache rafraichi: {payload['count']} resultat(s)")
