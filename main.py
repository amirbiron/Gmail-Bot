import os
import time
import json
import base64
import threading
import logging
from flask import Flask, request

from gmail_client import get_new_emails, get_emails_since, start_watch, PUBSUB_TOPIC
from telegram_client import send_notification, send_refresh_token_guide
from db import is_seen, mark_seen, get_history_id, set_history_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

POLL_INTERVAL = 120  # שניות
WATCH_RENEWAL_INTERVAL = 6 * 24 * 60 * 60  # 6 ימים (watch פג אחרי 7)
WEBHOOK_SECRET = os.environ.get("GMAIL_WEBHOOK_SECRET", "")

app = Flask(__name__)


@app.route("/")
def health():
    return "Gmail Bot is running", 200


# --- Webhook endpoint for Pub/Sub push ---


def _process_emails(emails):
    """עיבוד רשימת מיילים — שליחת התראה למיילים חדשים."""
    for email in emails:
        if not is_seen(email["id"]):
            send_notification(email)
            mark_seen(email["id"])
            logging.info(f"Notified: {email['subject']}")


@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint ש-Google Pub/Sub שולח אליו push notifications."""
    if WEBHOOK_SECRET:
        token = request.args.get("token", "")
        if token != WEBHOOK_SECRET:
            logging.warning("Webhook received with invalid token")
            return "Unauthorized", 401

    envelope = request.get_json(silent=True)
    if not envelope or "message" not in envelope:
        return "Bad Request", 400

    pubsub_message = envelope["message"]
    data = base64.urlsafe_b64decode(pubsub_message.get("data", "")).decode("utf-8")

    try:
        notification = json.loads(data)
    except json.JSONDecodeError:
        logging.error(f"Failed to parse Pub/Sub data: {data}")
        return "OK", 200

    logging.info(f"Webhook notification: emailAddress={notification.get('emailAddress')}, "
                 f"historyId={notification.get('historyId')}")

    history_id = get_history_id()
    if not history_id:
        logging.warning("No stored historyId, running full poll")
        try:
            emails = get_new_emails()
            _process_emails(emails)
        except Exception as e:
            logging.error(f"Error in webhook full poll: {e}")
        new_hid = notification.get("historyId")
        if new_hid:
            set_history_id(new_hid)
        return "OK", 200

    try:
        emails, new_history_id = get_emails_since(history_id)

        if emails is None:
            # historyId expired — fallback to full poll
            emails = get_new_emails()
            _process_emails(emails)
            new_history_id = notification.get("historyId")
        else:
            _process_emails(emails)

        if new_history_id:
            set_history_id(new_history_id)

    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        if "invalid_grant" in str(e).lower():
            logging.error("Refresh token expired — sending guide to Telegram")
            try:
                send_refresh_token_guide()
            except Exception as guide_err:
                logging.error(f"Failed to send refresh token guide: {guide_err}")

    return "OK", 200


# --- Watch renewal loop ---


def watch_renewal_loop():
    """חידוש watch() כל 6 ימים כדי לשמור על ה-push notifications פעילים."""
    while True:
        try:
            result = start_watch()
            if result:
                hid = result.get("historyId")
                if hid and not get_history_id():
                    set_history_id(hid)
        except Exception as e:
            logging.error(f"Error renewing watch: {e}")
            if "invalid_grant" in str(e).lower():
                try:
                    send_refresh_token_guide()
                except Exception:
                    pass
                return
        time.sleep(WATCH_RENEWAL_INTERVAL)


# --- Polling fallback loop ---


def polling_loop():
    """Fallback — polling רגיל למקרה שה-webhook לא פעיל."""
    logging.info("Gmail Bot polling started")
    while True:
        try:
            emails = get_new_emails()
            _process_emails(emails)
        except Exception as e:
            logging.error(f"Error in polling loop: {e}")
            if "invalid_grant" in str(e).lower():
                logging.error("Refresh token expired — sending guide to Telegram")
                try:
                    send_refresh_token_guide()
                    logging.info("Refresh token guide sent successfully")
                except Exception as guide_err:
                    logging.error(f"Failed to send refresh token guide: {guide_err}")
                return
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if PUBSUB_TOPIC:
        logging.info("Webhook mode enabled — starting watch renewal loop")
        thread = threading.Thread(target=watch_renewal_loop, daemon=True)
        thread.start()
    else:
        logging.info("No GOOGLE_PUBSUB_TOPIC — falling back to polling mode")
        thread = threading.Thread(target=polling_loop, daemon=True)
        thread.start()

    app.run(host="0.0.0.0", port=10000)
