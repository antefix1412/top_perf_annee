from __future__ import annotations

from app import results_filename, top3_as_text


def build_save_payload(results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "filename": results_filename(),
        "text": top3_as_text(results),
    }
