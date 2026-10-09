"""Minimal Google Drive v3 helpers: upload / list / create folder.

    from module.apis.google.drive import upload_file
    upload_file(r"C:\\path\\file.pdf", folder_id="<folder id or share link>")

The destination accepts either a raw folder ID or a full Drive folder link
(``https://drive.google.com/drive/folders/<ID>``); the ID is extracted for you.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .auth import load_credentials

_FOLDER_RE = re.compile(r"/folders/([A-Za-z0-9_-]+)")
_ID_RE = re.compile(r"[?&]id=([A-Za-z0-9_-]+)")


def extract_folder_id(value: str) -> str:
    """Accept a Drive folder URL or a raw ID and return the bare folder ID."""
    value = (value or "").strip()
    m = _FOLDER_RE.search(value)
    if m:
        return m.group(1)
    m = _ID_RE.search(value)
    if m:
        return m.group(1)
    return value


def get_service(credentials=None, scopes=None):
    """Build (and return) a Google Drive v3 client."""
    creds = credentials or load_credentials(scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_file(local_path, folder_id=None, name=None, service=None,
                mime_type=None, resumable=None):
    """Upload ``local_path`` into ``folder_id`` and return the created file info."""
    service = service or get_service()
    local_path = Path(local_path)
    if not local_path.is_file():
        raise FileNotFoundError(local_path)

    body = {"name": name or local_path.name}
    if folder_id:
        body["parents"] = [extract_folder_id(folder_id)]

    mime_type = mime_type or mimetypes.guess_type(local_path.name)[0]
    if resumable is None:
        resumable = local_path.stat().st_size > 5 * 1024 * 1024  # >5 MB

    media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=resumable)
    request = service.files().create(
        body=body,
        media_body=media,
        fields="id, name, parents, webViewLink, size",
        supportsAllDrives=True,
    )
    return request.execute()


def list_files(folder_id=None, service=None, query=None, page_size=100):
    """List files, optionally scoped to a parent folder."""
    service = service or get_service()
    parts = ["trashed = false"]
    if folder_id:
        parts.append(f"'{extract_folder_id(folder_id)}' in parents")
    if query:
        parts.append(query)
    resp = service.files().list(
        q=" and ".join(parts),
        pageSize=page_size,
        fields="files(id, name, mimeType, webViewLink, size)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return resp.get("files", [])


def create_folder(name, parent_id=None, service=None):
    """Create a folder (optionally inside ``parent_id``) and return its info."""
    service = service or get_service()
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [extract_folder_id(parent_id)]
    return service.files().create(
        body=body, fields="id, name, webViewLink", supportsAllDrives=True
    ).execute()
