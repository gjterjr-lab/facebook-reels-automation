"""TEMPORARY: slowly deletes every reel on every Page in FACEBOOK_PAGE_TOKENS.
Paced to stay under Facebook's request limit. Logs only counts."""
import json
import os
import re
import sys
import time

import requests

VERSION = os.environ.get("META_GRAPH_API_VERSION") or "v21.0"
BASE = f"https://graph.facebook.com/{VERSION}"
START_DELAY = 7200
DEADLINE = time.monotonic() + 20000
PAUSE = 25
LIMIT_WAIT = 900
LIMIT_CODES = {4, 17, 32, 613, 80001, 80002, 80004}


def code_of(error):
    response = getattr(error, "response", None)
    if response is None:
        return None
    try:
        return response.json().get("error", {}).get("code")
    except Exception:
        return None


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


def call(method, url, **kwargs):
    # Retries forever (until the deadline) when Facebook says "slow down".
    while True:
        try:
            response = requests.request(method, url, timeout=60, **kwargs)
            response.raise_for_status()
            return response
        except Exception as error:
            if code_of(error) in LIMIT_CODES and time.monotonic() < DEADLINE:
                print(f"Rate limit hit. Waiting {LIMIT_WAIT // 60} min.", flush=True)
                time.sleep(LIMIT_WAIT)
                continue
            raise


def list_reels(page_id, token):
    ids = []
    url = f"{BASE}/{page_id}/video_reels"
    params = {"fields": "id", "limit": 100, "access_token": token}
    while url:
        data = call("GET", url, params=params).json()
        ids += [item["id"] for item in data.get("data", [])]
        url = (data.get("paging") or {}).get("next")
        params = None
    return ids


def main():
    print(f"Waiting {START_DELAY // 60} min so Facebook's limit can clear.", flush=True)
    time.sleep(START_DELAY)
    tokens = json.loads(os.environ["FACEBOOK_PAGE_TOKENS"])
    pages = list(tokens.items())
    todo = {}
    for number, (page_id, token) in enumerate(pages, start=1):
        try:
            todo[number] = list_reels(page_id, token)
        except Exception as error:
            todo[number] = []
            print(f"Page {number}: list failed: {safe(error)}", flush=True)
    print("To delete: " + ", ".join(f"Page {n}: {len(v)}" for n, v in todo.items()), flush=True)

    deleted = {n: 0 for n in todo}
    failed = {n: 0 for n in todo}
    total = 0

    while any(todo.values()) and time.monotonic() < DEADLINE:
        for number, (page_id, token) in enumerate(pages, start=1):
            if not todo[number]:
                continue
            reel_id = todo[number].pop(0)
            try:
                call("DELETE", f"{BASE}/{reel_id}", params={"access_token": token})
                deleted[number] += 1
            except Exception as error:
                failed[number] += 1
                print(f"Page {number}: delete failed: {safe(error)}", flush=True)
            total += 1
            if total % 20 == 0:
                left = sum(len(v) for v in todo.values())
                print(f"Progress: {total} handled, {left} left", flush=True)
            time.sleep(PAUSE)

    for number, (page_id, token) in enumerate(pages, start=1):
        try:
            left = len(list_reels(page_id, token))
        except Exception as error:
            left = -1
        print(f"Page {number}: deleted {deleted[number]}, failed {failed[number]}, left {left}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Cleanup error:", safe(error))
        sys.exit(1)
