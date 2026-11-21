"""
Heads-Up: one-time Google setup and test.

1. Signs in to the Gloria TEST account (opens a browser the first time and saves token.json).
2. Creates Gloria's recurring pickup events on that test calendar (no alerts, just like her real phone).
3. Lists upcoming events to prove Calendar access works.

Run from the folder that contains credentials.json:
    python -m pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
    python setup_google.py
"""
import os
import datetime as dt

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Everything Heads-Up will need. If you ever change this list, delete token.json and run again.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",  # read and edit events
    "https://www.googleapis.com/auth/gmail.send",       # send the briefing and family emails
]
TZ = "America/Halifax"

# Gloria's repeating events, rebuilt from her persona calendar screenshot.
SEED_EVENTS = [
    {
        "summary": "Pick up Ava",
        "location": "Oakwood Elementary, front doors",
        "start": "2026-10-01T15:15:00",  # first Tuesday/Thursday on or after this date
        "end": "2026-10-01T15:45:00",
        "rrule": "RRULE:FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20261231T235959Z",
    },
    {
        "summary": "Pick up Noah",
        "location": "Daycare",
        "start": "2026-10-02T16:30:00",
        "end": "2026-10-02T17:00:00",
        "rrule": "RRULE:FREQ=WEEKLY;BYDAY=FR;UNTIL=20261231T235959Z",
    },
]


def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)  # sign in as the GLORIA test account
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds


def seed(service):
    existing = service.events().list(
        calendarId="primary", q="Pick up", singleEvents=False, maxResults=50
    ).execute().get("items", [])
    have = {e.get("summary") for e in existing if e.get("recurrence")}
    for ev in SEED_EVENTS:
        if ev["summary"] in have:
            print(f"Already there: {ev['summary']}")
            continue
        body = {
            "summary": ev["summary"],
            "location": ev["location"],
            "start": {"dateTime": ev["start"], "timeZone": TZ},
            "end": {"dateTime": ev["end"], "timeZone": TZ},
            "recurrence": [ev["rrule"]],
            "reminders": {"useDefault": False, "overrides": []},  # Alert: None, as in her data
        }
        created = service.events().insert(calendarId="primary", body=body).execute()
        print(f"Created: {created['summary']} -> {created.get('htmlLink')}")


def show_demo_week(service):
    # The demo week from the persona: Mon Oct 19 to Sun Oct 25, 2026.
    start = dt.datetime(2026, 10, 19, tzinfo=dt.timezone(dt.timedelta(hours=-3))).isoformat()
    end = dt.datetime(2026, 10, 26, tzinfo=dt.timezone(dt.timedelta(hours=-3))).isoformat()
    items = service.events().list(
        calendarId="primary", timeMin=start, timeMax=end,
        singleEvents=True, orderBy="startTime",
    ).execute().get("items", [])
    print("\nGloria's demo week (each repeat is its own occurrence with its own id):")
    for e in items:
        print(f"  {e['start'].get('dateTime')}  {e['summary']}   id={e['id']}")


if __name__ == "__main__":
    service = build("calendar", "v3", credentials=get_credentials())
    seed(service)
    show_demo_week(service)
    print("\nCalendar access works. token.json is saved; keep it and credentials.json out of Git.")
