"""TEMPORARY: deletes every reel on every Page in FACEBOOK_PAGE_TOKENS.
Logs only counts, never ids, names or tokens."""
import json
import os
import re
import sys

import requests

VERSION = os.environ.get("META_GRAPH_API_VERSION") or "v21.0"
BASE = f"https://graph.facebook.com/{VERSION}"


def safe(error):
    text = type(error).__name__
    response = getattr(error, "response", None)
    if response is not None:
        try:
            info = response.json().get("error", {})
            text += f" HTTP {response.status_code} code {info.get('code')}: {info.get('message', '')}"
        except Exception:
            text += f" HTTP {response.status_code}"
    text = re.sub(r"EAA[\w-]+", "<token>", text)
    return re.sub(r"\d{6,}", "<id>", text)[:200]


def list_reels(page_id, token):
    ids = []
    url = f"{BASE}/{page_id}/video_reels"
    params = {"fields": "id", "limit": 100, "access_token": token}
    while url:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        ids += [item["id"] for item in data.get("data", [])]
        url = (data.get("paging") or {}).get("next")
        params = None
    return ids


def main():
    tokens = json.loads(os.environ["FACEBOOK_PAGE_TOKENS"])
    for number, (page_id, token) in enumerate(tokens.items(), start=1):
        deleted = failed = 0
        error_seen = ""
        for _ in range(30):
            try:
                ids = list_reels(page_id, token)
            except Exception as error:
                error_seen = "list: " + safe(error)
                break
            if not ids:
                break
            progress = 0
            for reel_id in ids:
                try:
                    response = requests.delete(
                        f"{BASE}/{reel_id}",
                        params={"access_token": token},
                        timeout=60,
                    )
                    response.raise_for_status()
                    deleted += 1
                    progress += 1
                except Exception as error:
                    failed += 1
                    error_seen = "delete: " + safe(error)
            if not progress:
                break
        try:
            left = len(list_reels(page_id, token))
        except Exception as error:
            left = -1
            error_seen = error_seen or "list: " + safe(error)
        print(f"Page {number}: deleted {deleted}, failed {failed}, left {left}")
        if error_seen:
            print(f"Page {number} last error: {error_seen}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Cleanup error:", safe(error))
        sys.exit(1)
