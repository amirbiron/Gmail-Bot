import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# --- In-memory fallback ---
_seen_in_memory: set[str] = set()
_using_mongo = False

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

    MONGO_URI = os.environ.get("MONGODB_URI", "")
    DB_NAME = os.environ.get("MONGODB_DB", "gmail_bot")

    if MONGO_URI:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # בדיקת חיבור אמיתית
        client.admin.command("ping")
        db = client[DB_NAME]
        collection = db["seen_messages"]
        collection.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 30)
        _using_mongo = True
        logger.info("Connected to MongoDB successfully")
    else:
        logger.warning("MONGODB_URI not set — using in-memory fallback")

except Exception as e:
    logger.warning(f"MongoDB unavailable ({e}) — using in-memory fallback")


def is_seen(message_id: str) -> bool:
    if _using_mongo:
        try:
            return collection.find_one({"message_id": message_id}) is not None
        except Exception as e:
            logger.warning(f"MongoDB read failed ({e}) — checking in-memory")
            return message_id in _seen_in_memory
    return message_id in _seen_in_memory


def mark_seen(message_id: str):
    _seen_in_memory.add(message_id)
    if _using_mongo:
        try:
            collection.insert_one({
                "message_id": message_id,
                "created_at": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.warning(f"MongoDB write failed ({e}) — saved in-memory only")
