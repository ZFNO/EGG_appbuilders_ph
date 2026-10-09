# module.apis.google

Google Drive integration built on the official `google-api-python-client`.

## Auth (pick one)

Uploading to *your* Drive requires OAuth 2.0 - an **API key cannot upload**.
An API key only reads *public* data.

### Option A - OAuth client (recommended)
1. Google Cloud Console -> APIs & Services -> enable **Google Drive API**.
2. Credentials -> Create credentials -> **OAuth client ID** -> *Desktop app*.
3. Download the JSON and save it here as `credentials.json`
   (or set `GDRIVE_CREDENTIALS` to its path).
4. First upload opens a browser for consent and caches `token.json`
   (or `GDRIVE_TOKEN`). Later runs reuse it.

### Option B - Application Default Credentials (you already have gcloud)
```bat
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/drive
```
No `credentials.json` needed; `load_credentials()` falls back to ADC.

## Usage
```python
from module.apis.google.drive import upload_file

info = upload_file(r"C:\\data\\report.pdf", folder_id="https://drive.google.com/drive/folders/<FOLDER_ID>")
print(info["webViewLink"])
```

`folder_id` accepts a full share link or a bare ID.

## Files
- `auth.py`  - `load_credentials()` (OAuth / cached token / ADC)
- `drive.py` - `upload_file()`, `list_files()`, `create_folder()`, `get_service()`
