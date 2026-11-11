import hashlib
import json
import os
import re
import sys

from google_drive import (
    list_videos,
    download_video,
    get_published_pages,
    mark_page_published,
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
    page_numbers = {
        page_id: number
        for number, page_id in enumerate(page_tokens, start=1)
    }
    videos = list_videos(upload_folder_id)

    print(f"Found {len(videos)} video(s).")

    for video in videos:
        file_id = video["id"]
        filename = video["name"]
        label = tag(file_id)

        published_pages = get_published_pages(video)

        pending_pages = [
            page_id
            for page_id in page_tokens
            if page_id not in published_pages
        ]

        if not pending_pages:
            print(
                f"All Pages completed for {label}. "
                "Moving to Published."
            )
            move_to_published(
                file_id,
                upload_folder_id,
                published_folder_id,
            )
            continue

        print(
            f"Processing {label} for "
            f"{len(pending_pages)} Page(s)."
        )

        local_path = download_video(file_id, filename)
        published_now = 0

        for page_id in pending_pages:
            try:
                result = publish_reel(
                    page_id=page_id,
                    access_token=page_tokens[page_id],
                    video_path=local_path,
                    caption=caption,
                )

                if result["success"]:
                    published_now += 1
                    mark_page_published(
                        file_id,
                        page_id,
                        video,
                    )
                    print(
                        f"Published {label} "
                        f"to Page {page_numbers[page_id]}."
                    )

            except Exception as error:
                print(
                    f"Failed for Page {page_numbers[page_id]}: "
                    f"{type(error).__name__}"
                )

                detail = safe_error_text(error)

                if detail:
                    print(f"Facebook response: {detail}")

        updated_pages = get_published_pages(video)

        if all(
            page_id in updated_pages
            for page_id in page_tokens
        ):
            move_to_published(
                file_id,
                upload_folder_id,
                published_folder_id,
            )
            print(f"Completed all Pages for {label}.")
        else:
            print(
                f"{label} still has pending Pages. "
                "It will be retried."
            )

        # One video per run: as soon as a video was published to at least
        # one Page, stop here. The next video waits for the next run.
        # A video that could not be published anywhere does not use up the
        # run, so it can never block the videos behind it.
        if published_now:
            print("One video handled. The next one waits for the next run.")
            break


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = f": {error}" if isinstance(error, RuntimeError) else ""
        print(f"Automation error: {type(error).__name__}{detail}")
        sys.exit(1)
