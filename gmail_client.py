import os
import logging
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
SENDERS_FILTER = os.environ.get("GMAIL_SENDERS_FILTER", "")  # למשל: "submissions@formsubmit.co,other@example.com"
KEYWORDS_FILTER = os.environ.get("GMAIL_KEYWORDS_FILTER", "")  # למשל: "חשבונית,תשלום התקבל,דוח חודשי"
EXTRA_FILTER = os.environ.get("GMAIL_EXTRA_FILTER", "")  # למשל: "-category:promotions -category:social -category:updates -category:forums"
PUBSUB_TOPIC = os.environ.get("GOOGLE_PUBSUB_TOPIC", "")  # למשל: "projects/my-project/topics/gmail-notifications"

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


def _parse_message(service, msg_id):
    """שליפת פרטי הודעה לפי ID."""
    data = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
    return {
        "id": msg_id,
        "from": headers.get("From", "Unknown"),
        "subject": headers.get("Subject", "(ללא נושא)"),
        "date": headers.get("Date", ""),
        "snippet": data.get("snippet", ""),
        "body": extract_body(data["payload"]),
    }


def get_new_emails():
    """Polling fallback — שואב מיילים שלא נקראו לפי הפילטרים."""
    service = get_service()
    query = build_query()
    result = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
    messages = result.get("messages", [])

    emails = []
    for msg in messages:
        emails.append(_parse_message(service, msg["id"]))

    return emails


# --- Pub/Sub webhook support ---


def start_watch():
    """רישום ל-Gmail Push Notifications דרך Pub/Sub.

    מחזיר dict עם historyId ו-expiration, או None אם לא מוגדר topic.
    יש לחדש כל 7 ימים.
    """
    if not PUBSUB_TOPIC:
        logging.warning("GOOGLE_PUBSUB_TOPIC not set — webhook mode disabled")
        return None

    service = get_service()
    body = {
        "topicName": PUBSUB_TOPIC,
        "labelIds": ["INBOX"],
    }
    result = service.users().watch(userId="me", body=body).execute()
    logging.info(f"Gmail watch registered, historyId={result.get('historyId')}, "
                 f"expiration={result.get('expiration')}")
    return result


def get_emails_since(history_id):
    """שליפת הודעות חדשות מאז historyId מסוים באמצעות History API.

    מחזיר (emails, new_history_id).
    """
    service = get_service()

    try:
        response = service.users().history().list(
            userId="me",
            startHistoryId=history_id,
            historyTypes=["messageAdded"],
            labelId="INBOX",
        ).execute()
    except Exception as e:
        if "404" in str(e) or "notFound" in str(e).lower():
            logging.warning(f"historyId {history_id} expired, falling back to full poll")
            return None, None
        raise

    new_history_id = response.get("historyId", history_id)
    history = response.get("history", [])

    msg_ids = set()
    for record in history:
        for added in record.get("messagesAdded", []):
            msg = added.get("message", {})
            labels = msg.get("labelIds", [])
            if "INBOX" in labels:
                msg_ids.add(msg["id"])

    emails = []
    for msg_id in msg_ids:
        try:
            emails.append(_parse_message(service, msg_id))
        except Exception as e:
            logging.error(f"Failed to fetch message {msg_id}: {e}")

    return emails, new_history_id
