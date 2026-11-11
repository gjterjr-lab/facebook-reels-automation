import json
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


SCOPES = [
    "https://www.googleapis.com/auth/drive"
]


def get_drive_service():
    raw_credentials = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_JSON"
    )

    if not raw_credentials:
        raise RuntimeError(
            "Missing GOOGLE_SERVICE_ACCOUNT_JSON"
        )

    credentials_info = json.loads(raw_credentials)

    credentials = (
        service_account.Credentials
        .from_service_account_info(
            credentials_info,
            scopes=SCOPES,
        )
    )

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def list_videos(folder_id):
    service = get_drive_service()

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false"
    )

    response = service.files().list(
        q=query,
        pageSize=100,
        orderBy="createdTime",
        fields=(
            "files(id,name,mimeType,parents,appProperties)"
        ),
    ).execute()

    return [
        file
        for file in response.get("files", [])
        if file.get("mimeType", "").startswith("video/")
    ]


def download_video(file_id, filename):
    service = get_drive_service()

    output_dir = Path("incoming")
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / Path(filename).name

    request = service.files().get_media(
        fileId=file_id
    )

    with open(output_path, "wb") as output_file:
        downloader = MediaIoBaseDownload(
            output_file,
            request,
        )

        done = False

        while not done:
            _, done = downloader.next_chunk()

    return str(output_path)


def get_published_pages(file):
    app_properties = file.get("appProperties") or {}

    raw = app_properties.get(
        "published_page_ids",
        "[]",
    )

    return set(json.loads(raw))


def mark_page_published(file_id, page_id, file):
    service = get_drive_service()

    published_pages = get_published_pages(file)
    published_pages.add(str(page_id))

    app_properties = file.get("appProperties") or {}

    app_properties["published_page_ids"] = json.dumps(
        sorted(published_pages)
    )

    service.files().update(
        fileId=file_id,
        body={
            "appProperties": app_properties,
        },
        fields="id,appProperties",
    ).execute()

    file["appProperties"] = app_properties


def move_to_published(file_id, upload_folder_id,
                      published_folder_id):
    service = get_drive_service()

    service.files().update(
        fileId=file_id,
        addParents=published_folder_id,
        removeParents=upload_folder_id,
        fields="id,parents",
    ).execute()
