import os
import re
import html
import requests
from email.utils import parsedate_to_datetime

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
def _parse_chat_ids(raw):
    """פירסור TELEGRAM_CHAT_ID — תומך בפילטר לפי פרויקט.

    פורמט: "ID1,ID2:project,ID3:project"
    ID ללא פילטר מקבל את כל המיילים.
    """
    entries = []
    for part in raw.split(","):
        part = part.strip()
        if ":" in part:
            chat_id, project_filter = part.split(":", 1)
            entries.append((chat_id.strip(), project_filter.strip().lower()))
        else:
            entries.append((part, None))
    return entries


CHAT_ENTRIES = _parse_chat_ids(os.environ["TELEGRAM_CHAT_ID"])

FIELD_NAMES = {
    "name": "שם",
    "phone": "טלפון",
    "email": "אימייל",
    "business": "עסק",
    "groups": "קבוצות",
}

DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]

SENTRY_PROJECTS = ["codekeeper", "shipment-bot"]


def detect_sentry_project(email):
    """זיהוי שם פרויקט Sentry מתוך תוכן המייל."""
    searchable = " ".join([
        email.get("subject", ""),
        email.get("snippet", ""),
        email.get("body", ""),
    ]).lower()
    for project in SENTRY_PROJECTS:
        if project in searchable:
            return project
    return None

# סדר המפתחות חשוב — משתמשים בהם כעוגנים לפירסור
KNOWN_KEYS = list(FIELD_NAMES.keys())


def format_date(date_str):
    try:
        dt = parsedate_to_datetime(date_str)
        day = DAYS_HE[dt.weekday()]
        return dt.strftime(f"%H:%M {day} %d/%m/%Y")
    except Exception:
        return date_str


def parse_formsubmit_html(body_html):
    """פירסור טבלת HTML של FormSubmit — אמין יותר מפירסור snippet."""
    if not body_html:
        return None

    rows = re.findall(
        r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>",
        body_html, re.IGNORECASE | re.DOTALL,
    )
    if not rows:
        return None

    lines = []
    for raw_key, raw_value in rows:
        key = html.unescape(re.sub(r"<[^>]+>", "", raw_key)).strip().lower()
        value_text = html.unescape(re.sub(r"<[^>]+>", "", raw_value)).strip()
        # דילוג על שורת הכותרת "Name | Value"
        if key == "name" and value_text.lower() == "value":
            continue
        label = FIELD_NAMES.get(key)
        if label is None:
            continue
        if value_text:
            lines.append(f"*{label}:* {value_text}")
        else:
            lines.append(f"*{label}:*")

    return "\n".join(lines) if lines else None


def parse_formsubmit_snippet(snippet):
    """פירסור snippet — fallback למקרה שאין body."""
    clean = html.unescape(snippet)

    match = re.search(r"Here.s what they had to say[:\s]*(.*)", clean, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    body = match.group(1).strip()

    body = re.sub(r"^Name\s+Value\s*", "", body, flags=re.IGNORECASE).strip()

    keys_pattern = "|".join(KNOWN_KEYS)
    pattern = re.compile(
        rf"({keys_pattern})\s+(.*?)(?=\s+(?:{keys_pattern})\s|$)",
        re.IGNORECASE | re.DOTALL
    )

    matches = pattern.findall(body)
    if not matches:
        return None

    lines = []
    for key, value in matches:
        value = value.strip()
        label = FIELD_NAMES.get(key.lower(), key)
        if value:
            lines.append(f"*{label}:* {value}")
        else:
            lines.append(f"*{label}:*")

    return "\n".join(lines)


def _header_title(project):
    if project == "shipment-bot":
        return f"📧 *מייל חדש — {project}* 🚚"
    if project:
        return f"📧 *מייל חדש — {project}*"
    return "📧 *מייל חדש*"


def format_formsubmit(email, project=None):
    fields = parse_formsubmit_html(email.get("body", "")) or parse_formsubmit_snippet(email["snippet"])
    date_str = format_date(email["date"])
    link = f"https://mail.google.com/mail/u/0/#inbox/{email['id']}"
    header = (
        f"{_header_title(project)}\n\n"
        f"👤 *מאת:* `{email['from']}`\n"
        f"📌 *נושא:* {email['subject']}\n"
        f"🕐 *תאריך:* {date_str}\n"
        f"🔗 [פתח ב-Gmail]({link})\n\n"
    )
    if fields:
        return header + "*פרטי הטופס:*\n" + fields
    return header + f"_{html.unescape(email['snippet'])}_"


def format_default(email, project=None):
    date_str = format_date(email["date"])
    link = f"https://mail.google.com/mail/u/0/#inbox/{email['id']}"
    return (
        f"{_header_title(project)}\n\n"
        f"👤 *מאת:* `{email['from']}`\n"
        f"📌 *נושא:* {email['subject']}\n"
        f"🕐 *תאריך:* {date_str}\n"
        f"🔗 [פתח ב-Gmail]({link})\n\n"
        f"_{html.unescape(email['snippet'])}_"
    )


def send_notification(email):
    sender = email["from"].lower()
    project = detect_sentry_project(email)
    if "formsubmit" in sender:
        text = format_formsubmit(email, project)
    else:
        text = format_default(email, project)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id, project_filter in CHAT_ENTRIES:
        if project_filter and project_filter != project:
            continue
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
