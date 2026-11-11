import os
from pathlib import Path

import requests


def publish_reel(
    page_id,
    access_token,
    video_path,
    caption="",
):
    api_version = os.environ.get(
        "META_GRAPH_API_VERSION"
    )

    if not api_version:
        raise RuntimeError(
            "Missing META_GRAPH_API_VERSION"
        )

    base_url = (
        f"https://graph.facebook.com/"
        f"{api_version}/{page_id}/video_reels"
    )

    # Start the Reel upload
    start_response = requests.post(
        base_url,
        params={
            "upload_phase": "start",
            "access_token": access_token,
        },
        timeout=60,
    )

    start_response.raise_for_status()
    upload_data = start_response.json()

    video_id = upload_data["video_id"]
    upload_url = upload_data["upload_url"]

    # Upload the video
    file_size = Path(video_path).stat().st_size

    with open(video_path, "rb") as video_file:
        upload_response = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
            data=video_file,
            timeout=600,
        )

    upload_response.raise_for_status()

    # Finish and publish the Reel
    finish_response = requests.post(
        base_url,
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": caption,
            "access_token": access_token,
        },
        timeout=120,
    )

    finish_response.raise_for_status()

    result = finish_response.json()

    if result.get("success") is not True:
        raise RuntimeError(
            "Facebook did not confirm publishing"
        )

    return {
        "video_id": video_id,
        "success": True,
    }
