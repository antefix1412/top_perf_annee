from __future__ import annotations

import os

import requests


if __name__ == "__main__":
    base_url = os.getenv("FFTT_WEB_URL", "http://127.0.0.1:5000")
    response = requests.get(f"{base_url}/ping", timeout=10)
    print(response.status_code)
    print(response.text)
