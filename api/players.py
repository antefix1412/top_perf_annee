from __future__ import annotations

from app import app as application
from app import CLUB_NUM, get_club_players_cached


def build_players_payload(force_refresh: bool = False) -> dict[str, object]:
    players = get_club_players_cached(force_refresh=force_refresh)
    return {
        "club": CLUB_NUM,
        "count": len(players),
        "players": players,
    }
