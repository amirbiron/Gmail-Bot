import os
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
SENDERS_FILTER = os.environ.get("GMAIL_SENDERS_FILTER", "")  # למשל: "submissions@formsubmit.co,other@example.com"


def get_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("gmail", "v1", credentials=creds)


def build_query():
    if not SENDERS_FILTER:
        return "is:unread"
    senders = [s.strip() for s in SENDERS_FILTER.split(",") if s.strip()]
    from_query = " OR ".join([f"from:{s}" for s in senders])
    return f"is:unread ({from_query})"


def get_new_emails():
    service = get_service()
    query = build_query()
    result = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
    messages = result.get("messages", [])

    emails = []
    for msg in messages:
        data = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
                                               metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "(ללא נושא)"),
            "date": headers.get("Date", ""),
            "snippet": data.get("snippet", ""),
        })

    return emails
