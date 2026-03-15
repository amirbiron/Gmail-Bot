import time
import threading
import logging
from flask import Flask
from gmail_client import get_new_emails
from telegram_client import send_notification
from db import is_seen, mark_seen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

POLL_INTERVAL = 120  # שניות

app = Flask(__name__)


@app.route("/")
def health():
    return "Gmail Bot is running", 200


def polling_loop():
    logging.info("Gmail Bot started")
    while True:
        try:
            emails = get_new_emails()
            for email in emails:
                if not is_seen(email["id"]):
                    send_notification(email)
                    mark_seen(email["id"])
                    logging.info(f"Notified: {email['subject']}")
        except Exception as e:
            logging.error(f"Error in polling loop: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=10000)
