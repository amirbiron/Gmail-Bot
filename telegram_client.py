import os
import re
import html
import requests
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

# סדר המפתחות חשוב — משתמשים בהם כעוגנים לפירסור
KNOWN_KEYS = list(FIELD_NAMES.keys())


def format_date(date_str):
    try:
        dt = parsedate_to_datetime(date_str)
        day = DAYS_HE[dt.weekday()]
        return dt.strftime(f"%H:%M {day} %d/%m/%Y")
    except Exception:
        return date_str


def parse_formsubmit(snippet):
    clean = html.unescape(snippet)

    # חיתוך הכותרת
    match = re.search(r"Here.s what they had to say[:\s]*(.*)", clean, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    body = match.group(1).strip()

    # מחיקת שורת הכותרת "Name Value" אם קיימת
    body = re.sub(r"^Name\s+Value\s*", "", body, flags=re.IGNORECASE).strip()

    # בניית regex דינמי לפי המפתחות הידועים
    # כל מפתח הוא עוגן — הערך שלו הוא הכל עד המפתח הבא
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
