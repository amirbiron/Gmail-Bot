import os
from pymongo import MongoClient

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "gmail_bot")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db["seen_messages"]

# אינדקס כדי שלא יצטבר זבל לנצח (שמור הודעות 30 יום)
collection.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 30)


def is_seen(message_id: str) -> bool:
    return collection.find_one({"message_id": message_id}) is not None


def mark_seen(message_id: str):
    from datetime import datetime, timezone
    collection.insert_one({
        "message_id": message_id,
        "created_at": datetime.now(timezone.utc),
    })
