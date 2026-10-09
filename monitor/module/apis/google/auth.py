"""Credential helpers for the Google API modules.

Two ways to authenticate, in priority order:

1. OAuth "installed app" flow  -> put ``credentials.json`` (a *Desktop app*
   OAuth client from Google Cloud) next to this file (or point
   ``GDRIVE_CREDENTIALS`` at it). The first run opens a browser, the user
   consents, and a reusable ``token.json`` is cached (or ``GDRIVE_TOKEN``).
2. Application Default Credentials -> ``gcloud auth application-default login``

An API key is NOT enough to upload to a user's Drive; OAuth (or a service
account) is required.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SCOPES = ["https://www.googleapis.com/auth/drive"]

_HERE = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS = _HERE / "credentials.json"
DEFAULT_TOKEN = _HERE / "token.json"


def load_credentials(scopes=None, credentials_path=None, token_path=None,
                     allow_adc=True):
    """Return valid Google credentials using OAuth, a cached token, or ADC."""
    scopes = list(scopes or DEFAULT_SCOPES)
    credentials_path = Path(
        credentials_path or os.environ.get("GDRIVE_CREDENTIALS") or DEFAULT_CREDENTIALS
    )
    token_path = Path(
        token_path or os.environ.get("GDRIVE_TOKEN") or DEFAULT_TOKEN
    )

    creds = None

    # 1) A previously cached user token.
    if token_path.exists():
        from google.oauth2.credentials import Credentials
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except Exception:
            creds = None

    # 2) Refresh it, or run the interactive flow / fall back to ADC.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        elif credentials_path.exists():
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), scopes
            )
            creds = flow.run_local_server(port=0)
        elif allow_adc:
            import google.auth
            creds, _project = google.auth.default(scopes=scopes)
        else:
            raise FileNotFoundError(
                f"No credentials found. Expected an OAuth client at "
                f"{credentials_path} (or set GDRIVE_CREDENTIALS), or run "
                f"'gcloud auth application-default login'."
            )

    # 3) Cache the user token for next time (ADC objects have no to_json).
    if creds is not None and hasattr(creds, "to_json"):
        try:
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            pass

    return creds
