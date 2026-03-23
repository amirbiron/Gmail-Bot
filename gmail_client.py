import os
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
SENDERS_FILTER = os.environ.get("GMAIL_SENDERS_FILTER", "")  # למשל: "submissions@formsubmit.co,other@example.com"
KEYWORDS_FILTER = os.environ.get("GMAIL_KEYWORDS_FILTER", "")  # למשל: "חשבונית,תשלום התקבל,דוח חודשי"
EXTRA_FILTER = os.environ.get("GMAIL_EXTRA_FILTER", "")  # למשל: "-category:promotions -category:social -category:updates -category:forums"


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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
    conditions = []

    if SENDERS_FILTER:
        senders = [s.strip() for s in SENDERS_FILTER.split(",") if s.strip()]
        from_query = " OR ".join([f"from:{s}" for s in senders])
        conditions.append(f"({from_query})")

    if KEYWORDS_FILTER:
        keywords = [k.strip() for k in KEYWORDS_FILTER.split(",") if k.strip()]
        # עוטפים בגרשיים כדי לתמוך בצמדי מילים
        kw_query = " OR ".join([f'"{k}"' for k in keywords])
        conditions.append(f"({kw_query})")

    extra = f" {EXTRA_FILTER}" if EXTRA_FILTER else ""

    if not conditions:
        return f"is:unread{extra}"

    return f"is:unread ({' OR '.join(conditions)}){extra}"


def _collect_parts(payload):
    """אסוף את כל ה-parts באופן רקורסיבי (multipart מקונן)."""
    parts = []
    body_data = payload.get("body", {}).get("data")
    if body_data:
        parts.append(payload)
    for child in payload.get("parts", []):
        parts.extend(_collect_parts(child))
    return parts


def extract_body(payload):
    """שליפת גוף המייל (HTML מועדף, אחרת טקסט) מתוך payload של Gmail API."""
    all_parts = _collect_parts(payload)
    for mime in ("text/html", "text/plain"):
        for part in all_parts:
            if part.get("mimeType", "") == mime:
                data = part.get("body", {}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return ""


def get_new_emails():
    service = get_service()
    query = build_query()
    result = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
    messages = result.get("messages", [])

    emails = []
    for msg in messages:
        data = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "(ללא נושא)"),
            "date": headers.get("Date", ""),
            "snippet": data.get("snippet", ""),
            "body": extract_body(data["payload"]),
        })

    return emails
