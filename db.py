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


# --- History ID tracking for Pub/Sub webhook ---

state_collection = db["bot_state"]


def get_history_id():
    """מחזיר את ה-historyId האחרון ששמרנו, או None."""
    doc = state_collection.find_one({"_id": "history_id"})
    return doc["value"] if doc else None


def set_history_id(history_id: str):
    """שומר את ה-historyId האחרון."""
    state_collection.update_one(
        {"_id": "history_id"},
        {"$set": {"value": history_id}},
        upsert=True,
    )
