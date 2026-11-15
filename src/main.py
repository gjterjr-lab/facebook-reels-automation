import hashlib
import json
import os
import re
import sys

from google_drive import (
    list_videos,
    download_video,
    get_published_pages,
    mark_posted,
    last_posted_page,
    move_to_published,
)

from facebook_api import publish_reel


def load_page_tokens():
    raw = os.environ.get("FACEBOOK_PAGE_TOKENS")

    if not raw:
        raise RuntimeError("Missing FACEBOOK_PAGE_TOKENS")

    tokens = json.loads(raw)

    if not isinstance(tokens, dict) or not tokens:
        raise RuntimeError(
            "FACEBOOK_PAGE_TOKENS must be a non-empty JSON object"
        )

    return {
        str(page_id): token
        for page_id, token in tokens.items()
    }


def tag(value):
    # Short anonymous label for logs. Workflow logs of a public repo are
    # public, so file names and Page ids are never printed.
    return "#" + hashlib.sha1(str(value).encode()).hexdigest()[:6]


def safe_error_text(error):
    # Short description of a Facebook error that is safe to show in a public
    # log: no URLs (they contain the access token), no ids.
    response = getattr(error, "response", None)

    if response is None:
        return ""

    try:
        info = response.json().get("error", {})
        text = (
            f"HTTP {response.status_code}, "
            f"code {info.get('code')}: {info.get('message', '')}"
        )
    except Exception:
        text = f"HTTP {response.status_code}"

    text = re.sub(r"EAA[\w-]+", "<token>", text)
    text = re.sub(r"\d{6,}", "<id>", text)

    return text[:200]


def main():
    upload_folder_id = os.environ.get("GOOGLE_UPLOAD_FOLDER_ID")
    published_folder_id = os.environ.get("GOOGLE_PUBLISHED_FOLDER_ID")
    caption = os.environ.get("DEFAULT_CAPTION", "")

    if not upload_folder_id or not published_folder_id:
        raise RuntimeError("Missing Google Drive folder IDs")

    page_tokens = load_page_tokens()
    order = list(page_tokens)
    page_numbers = {
        page_id: number
        for number, page_id in enumerate(order, start=1)
    }
    videos = list_videos(upload_folder_id)

    print(f"Found {len(videos)} video(s).")

    # Rotation: one video goes to ONE Page. The Page that got the previous
    # video is remembered on that video in the Published folder, so this
    # round continues with the next Page in order and wraps to the first.
    last_page = last_posted_page(published_folder_id)

    if last_page in order:
        start = (order.index(last_page) + 1) % len(order)
    else:
        start = 0

    turn = order[start:] + order[:start]

    for video in videos:
        file_id = video["id"]
        filename = video["name"]
        label = tag(file_id)

        if get_published_pages(video):
            # Already posted before (old all-Pages mode): do not post again.
            print(f"{label} was already posted. Moving to Published.")
            move_to_published(
                file_id,
                upload_folder_id,
                published_folder_id,
            )
            continue

        print(
            f"Processing {label}. "
            f"This turn: Page {page_numbers[turn[0]]}."
        )

        local_path = download_video(file_id, filename)

        for page_id in turn:
            try:
                result = publish_reel(
                    page_id=page_id,
                    access_token=page_tokens[page_id],
                    video_path=local_path,
                    caption=caption,
                )
            except Exception as error:
                print(
                    f"Failed for Page {page_numbers[page_id]}: "
                    f"{type(error).__name__}"
                )

                detail = safe_error_text(error)

                if detail:
                    print(f"Facebook response: {detail}")

                continue

            if result["success"]:
                mark_posted(file_id, page_id, video)
                move_to_published(
                    file_id,
                    upload_folder_id,
                    published_folder_id,
                )
                print(
                    f"Published {label} "
                    f"to Page {page_numbers[page_id]}. "
                    "Next video goes to the next Page."
                )
                # One video, one Page, then the run ends (10 min wait).
                return

        print(f"{label} could not be published to any Page. Will retry.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = f": {error}" if isinstance(error, RuntimeError) else ""
        print(f"Automation error: {type(error).__name__}{detail}")
        sys.exit(1)
