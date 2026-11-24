"""Google sign-in for the Gloria TEST account (same scopes and files as setup_google.py).

credentials.json (OAuth client) and token.json (saved sign-in) live in the repo
root and are git-ignored. The first run opens a browser to sign in.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",  # read and edit events
    "https://www.googleapis.com/auth/gmail.send",       # stretch goal: real emails
]


def get_credentials(root: Path = ROOT):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token, secrets = root / "token.json", root / "credentials.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secrets.exists():
                raise FileNotFoundError(f"Missing {secrets}. Download the OAuth client from Google Cloud Console.")
            creds = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def calendar_service(root: Path = ROOT):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=get_credentials(root), cache_discovery=False)
