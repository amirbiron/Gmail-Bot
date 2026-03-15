import os
import re
import html
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

FIELD_NAMES = {
    "name": "שם",
    "phone": "טלפון",
    "email": "אימייל",
    "business": "עסק",
    "groups": "קבוצות",
}

DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def format_date(date_str):
    try:
        dt = parsedate_to_datetime(date_str)
        day = DAYS_HE[dt.weekday()]
        return dt.strftime(f"%H:%M {day} %d/%m/%Y")
    except Exception:
        return date_str


def parse_formsubmit(snippet):
    """מפרסר את תוכן מייל FormSubmit לשדות מסודרים."""
    clean = html.unescape(snippet)
    # חיתוך הכותרת של FormSubmit
    match = re.search(r"Here.s what they had to say[:\s]*(.*)", clean, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    body = match.group(1).strip()
    # פירסור שדות — פורמט: "key value key value..."
    pairs = re.findall(r"(\w+)\s+([^\n\t]+?)(?=\s+\w+\s+|$)", body)
    if not pairs:
        return None
    lines = []
    for key, value in pairs:
        value = value.strip()
        label = FIELD_NAMES.get(key.lower(), key)
        if value:
            lines.append(f"*{label}:* {value}")
        # שדות ריקים — משאירים (לפי הבקשה)
        else:
            lines.append(f"*{label}:*")
    return "\n".join(lines)


def format_formsubmit(email):
    fields = parse_formsubmit(email["snippet"])
    date_str = format_date(email["date"])
    header = (
        f"📧 *מייל חדש*\n\n"
        f"👤 *מאת:* `{email['from']}`\n"
        f"📌 *נושא:* {email['subject']}\n"
        f"🕐 *תאריך:* {date_str}\n\n"
    )
    if fields:
        return header + "*פרטי הטופס:*\n" + fields
    return header + f"_{html.unescape(email['snippet'])}_"


def format_default(email):
    date_str = format_date(email["date"])
    return (
        f"📧 *מייל חדש*\n\n"
        f"👤 *מאת:* `{email['from']}`\n"
        f"📌 *נושא:* {email['subject']}\n"
        f"🕐 *תאריך:* {date_str}\n\n"
        f"_{html.unescape(email['snippet'])}_"
    )


def send_notification(email):
    sender = email["from"].lower()
    if "formsubmit" in sender:
        text = format_formsubmit(email)
    else:
        text = format_default(email)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
