import os
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def send_notification(email):
    text = (
        f"📧 *מייל חדש*\n\n"
        f"👤 *מאת:* `{email['from']}`\n"
        f"📌 *נושא:* {email['subject']}\n"
        f"🕐 *תאריך:* {email['date']}\n\n"
        f"_{email['snippet']}_"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
