from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import requests
from flask import Flask, Response, jsonify, render_template, request, send_file

from cache_store import clear_cache, get_cache, set_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent
CACHE_TTL_SECONDS = int(os.getenv("FFTT_CACHE_TTL_SECONDS", "900"))
CACHE_KEY_PLAYERS = "club_players"
CACHE_KEY_TOP3 = "top3_results"

MOTDEPASSE = os.getenv("FFTT_PASSWORD", "g2XCYk1eK3")
ID_APP = os.getenv("FFTT_ID_APP", "SW436")
SERIE = os.getenv("FFTT_SERIE", "RSJKKEQZCLBACUX")
CLUB_NUM = os.getenv("FFTT_CLUB_NUM", "03350022")
BASE_URL = os.getenv("FFTT_BASE_URL", "https://apiv2.fftt.com/mobile/pxml/")
DEFAULT_TIMEOUT = int(os.getenv("FFTT_TIMEOUT_SECONDS", "30"))

app = Flask(__name__, template_folder="templates", static_folder="static")


def generate_auth_params() -> dict[str, str]:
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    ccle = hashlib.md5(MOTDEPASSE.encode()).hexdigest()
    tmc = hmac.new(ccle.encode(), timestamp.encode(), hashlib.sha1).hexdigest()
    return {"serie": SERIE, "tm": timestamp, "tmc": tmc, "id": ID_APP}


def make_request(endpoint: str, additional_params: dict[str, str] | None = None, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    params = generate_auth_params()
    if additional_params:
        params.update(additional_params)

    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        response.encoding = "latin-1"
        try:
            return response.text.encode("latin-1").decode("utf-8", errors="ignore")
        except Exception:
            return response.text
    except requests.RequestException as exc:
        logging.error("Erreur API FFTT: %s", exc)
        return None


def parse_classement(value: str | None) -> int:
    if not value:
        return 0
    try:
        cleaned = value.split("-")[-1].strip() if "-" in value else value.strip()
        return int(float(cleaned))
    except Exception:
        return 0


def parse_match_date(value: str | None) -> datetime | None:
    if not value or value == "N/A":
        return None

    cleaned = value.strip()
    date_formats = (
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d-%m-%y",
    )
    for date_format in date_formats:
        try:
            return datetime.strptime(cleaned, date_format)
        except ValueError:
            continue
    return None


def school_year_start(date_value: datetime) -> int:
    return date_value.year if date_value.month >= 9 else date_value.year - 1


def is_current_school_year(date_value: str | None, reference: datetime | None = None) -> bool:
    parsed_date = parse_match_date(date_value)
    if parsed_date is None:
        return False

    current_reference = reference or datetime.now()
    return school_year_start(parsed_date) == school_year_start(current_reference)


def get_club_players() -> list[dict[str, str]]:
    content = make_request("xml_liste_joueur_o.php", {"club": CLUB_NUM, "valid": "1"})
    players: list[dict[str, str]] = []
    if not content:
        return players

    try:
        root = ET.fromstring(content)
        for joueur in root.findall("joueur"):
            licence = (joueur.findtext("licence") or "").strip()
            nom = (joueur.findtext("nom") or "").strip()
            prenom = (joueur.findtext("prenom") or "").strip()
            if licence and nom and prenom:
                players.append({"licence": licence, "nom": nom, "prenom": prenom})
    except ET.ParseError as exc:
        logging.error("Erreur parsing XML joueurs: %s", exc)
    return players


def get_player_points(licence: str) -> int | None:
    content = make_request("xml_licence_b.php", {"licence": licence})
    if not content:
        return None

    try:
        root = ET.fromstring(content)
        if root.findtext("error"):
            return None

        pointm = root.findtext("licence/pointm")
        point = root.findtext("licence/point")

        for raw in (pointm, point):
            if raw and raw.strip():
                try:
                    return int(float(raw.strip()))
                except (ValueError, TypeError):
                    continue
        return None
    except ET.ParseError:
        return None


def get_matches_for_player(licence: str) -> list[dict[str, Any]]:
    content = make_request("xml_partie.php", {"numlic": licence})
    if not content:
        return []

    matches: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(content)
        for partie in root.findall(".//resultat") + root.findall(".//partie"):
            matches.append(
                {
                    "date": partie.findtext("date", default="N/A"),
                    "adversaire": partie.findtext("nom", default="N/A"),
                    "victoire": partie.findtext("victoire", default="N/A"),
                    "classement_adv": parse_classement(partie.findtext("classement", default="0")),
                }
            )
    except ET.ParseError:
        return []
    return matches


def get_top3_results(force_refresh: bool = False) -> list[dict[str, Any]]:
    if not force_refresh:
        cached = get_cache(CACHE_KEY_TOP3, max_age_seconds=CACHE_TTL_SECONDS)
        if cached:
            return cached.get("results", [])

    players = get_club_players_cached(force_refresh=force_refresh)
    if not players:
        return []

    results: list[dict[str, Any]] = []
    for player in players:
        joueur_points = get_player_points(player["licence"])
        if joueur_points is None:
            continue

        matches = get_matches_for_player(player["licence"])
        if not matches:
            continue

        for match in matches:
            if not is_current_school_year(match.get("date")):
                continue

            if match.get("victoire") == "V" and match.get("classement_adv", 0) >= joueur_points + 75:
                classement_adv = int(match["classement_adv"])
                ecart = classement_adv - joueur_points
                results.append(
                    {
                        "prenom": player["prenom"],
                        "nom": player["nom"],
                        "points_joueur": joueur_points,
                        "points_adv": classement_adv,
                        "ecart": ecart,
                        "date": match.get("date", "N/A"),
                    }
                )

    results.sort(key=lambda item: item["ecart"], reverse=True)
    top_results = results
    payload = build_top3_payload(top_results)
    set_cache(CACHE_KEY_TOP3, payload)
    return top_results


def get_club_players_cached(force_refresh: bool = False) -> list[dict[str, str]]:
    if not force_refresh:
        cached = get_cache(CACHE_KEY_PLAYERS, max_age_seconds=CACHE_TTL_SECONDS)
        if cached:
            return cached.get("players", [])

    players = get_club_players()
    payload = {
        "club": CLUB_NUM,
        "players": players,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    set_cache(CACHE_KEY_PLAYERS, payload)
    return players


def build_top3_payload(results: list[dict[str, Any]], *, source: str = "fftt") -> dict[str, Any]:
    return {
        "club": CLUB_NUM,
        "count": len(results),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "results": results,
    }


def refresh_all_cache() -> dict[str, Any]:
    clear_cache(CACHE_KEY_PLAYERS)
    clear_cache(CACHE_KEY_TOP3)
    results = get_top3_results(force_refresh=True)
    return build_top3_payload(results, source="fftt-refresh")


def top3_as_text(results: list[dict[str, Any]]) -> str:
    lines = ["TOP 3 DES PERFORMANCES FFTT", "=" * 60, ""]
    medals = ["1re place", "2e place", "3e place"]
    for index, result in enumerate(results):
        rank = medals[index] if index < len(medals) else f"{index + 1}e place"
        lines.append(f"{rank}: {result['prenom']} {result['nom']}")
        lines.append(f"Date: {result['date']}")
        lines.append(
            f"Performance: {result['points_joueur']} pts -> {result['points_adv']} pts (+{result['ecart']} points)"
        )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def results_filename() -> str:
    return f"{datetime.now().strftime('%Y-%m-%d')}_top3_perf.txt"


def load_top3_payload(force_refresh: bool = False) -> dict[str, Any]:
    if force_refresh:
        clear_cache(CACHE_KEY_TOP3)
    results = get_top3_results(force_refresh=force_refresh)
    payload = build_top3_payload(results)
    set_cache(CACHE_KEY_TOP3, payload)
    return payload


@app.route("/")
def index() -> str:
    return render_template("index.html", club_num=CLUB_NUM)


@app.route("/ping")
def ping() -> Response:
    return jsonify({"status": "ok", "service": "fftt-top3-web", "club": CLUB_NUM})


@app.route("/api/players")
def api_players() -> Response:
    force_refresh = request.args.get("refresh", "0") in {"1", "true", "yes"}
    players = get_club_players_cached(force_refresh=force_refresh)
    payload = {
        "club": CLUB_NUM,
        "count": len(players),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "players": players,
    }
    return jsonify(payload)


@app.route("/api/top3")
def api_top3() -> Response:
    force_refresh = request.args.get("refresh", "0") in {"1", "true", "yes"}
    payload = load_top3_payload(force_refresh=force_refresh)
    payload["text"] = top3_as_text(payload.get("results", []))
    return jsonify(payload)


@app.route("/api/refresh", methods=["POST", "GET"])
def api_refresh() -> Response:
    payload = refresh_all_cache()
    payload["text"] = top3_as_text(payload.get("results", []))
    return jsonify(payload)


@app.route("/api/save", methods=["POST", "GET"])
def api_save() -> Response:
    force_refresh = request.args.get("refresh", "0") in {"1", "true", "yes"}
    payload = load_top3_payload(force_refresh=force_refresh)
    text = top3_as_text(payload.get("results", []))
    buffer = BytesIO(text.encode("utf-8"))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="text/plain; charset=utf-8",
        as_attachment=True,
        download_name=results_filename(),
    )


@app.route("/api/status")
def api_status() -> Response:
    cached_top3 = get_cache(CACHE_KEY_TOP3, max_age_seconds=CACHE_TTL_SECONDS)
    cached_players = get_cache(CACHE_KEY_PLAYERS, max_age_seconds=CACHE_TTL_SECONDS)
    return jsonify(
        {
            "status": "ok",
            "club": CLUB_NUM,
            "cache": {
                "top3": bool(cached_top3),
                "players": bool(cached_players),
            },
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
