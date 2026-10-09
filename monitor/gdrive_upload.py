"""Upload files to a Google Drive folder from the terminal.

    python gdrive_upload.py <local_file_or_dir> [--folder <link_or_id>] [--name NAME]
                            [--dry-run] [--list]

Default folder is the one baked in below (override with --folder).
Auth: see module/apis/google/README.md (OAuth credentials.json OR gcloud ADC).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `module.*` importable when run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from module.apis.google.drive import (  # noqa: E402
    extract_folder_id,
    get_service,
    list_files,
    upload_file,
)

DEFAULT_FOLDER = "https://drive.google.com/drive/folders/1dI1ixawompk3wwe4S5GY1D_FTMGJQITN"


def iter_local(path: Path):
    if path.is_dir():
        yield from (p for p in path.rglob("*") if p.is_file())
    else:
        yield path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Upload files/folders to Google Drive.")
    ap.add_argument("path", nargs="?", help="local file or directory to upload")
    ap.add_argument("--folder", default=DEFAULT_FOLDER, help="Drive folder link or ID")
    ap.add_argument("--name", help="override the uploaded file name")
    ap.add_argument("--list", action="store_true", help="list the folder and exit")
    ap.add_argument("--dry-run", action="store_true", help="show what would upload")
    args = ap.parse_args(argv)

    folder_id = extract_folder_id(args.folder)
    print(f"[i] Target folder ID: {folder_id}")

    if args.list:
        service = get_service()
        for f in list_files(folder_id, service=service):
            print(f"  - {f['name']}  ({f.get('size','?')} bytes)  {f.get('webViewLink','')}")
        return 0

    if not args.path:
        ap.error("provide a path to upload (or use --list)")

    src = Path(args.path)
    if not src.exists():
        print(f"[x] not found: {src}")
        return 1

    files = list(iter_local(src))
    print(f"[i] {len(files)} file(s) to upload from {src}")

    if args.dry_run:
        for p in files:
            print(f"  -> {p}")
        return 0

    service = get_service()
    for p in files:
        name = args.name if (args.name and len(files) == 1) else None
        info = upload_file(p, folder_id=folder_id, name=name, service=service)
        print(f"[+] {p.name} -> id={info['id']}  {info.get('webViewLink','')}")
    print("[ok] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
