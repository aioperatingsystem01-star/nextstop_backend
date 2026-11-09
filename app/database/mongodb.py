
# ==============================================================================
# NEXT STOP BACKEND - MONGODB ATLAS CONNECTION & INDEXING
# Updated: 2026-11-09 | Non-blocking startup, certifi CA bundle, auto-retry
# ==============================================================================
import asyncio
import logging
import os
from typing import Optional

import certifi
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection,
)
from pymongo import ASCENDING, DESCENDING

from app.core.config import settings

logger = logging.getLogger("nextstop.database")


class MongoDB:
    """Singleton holder for MongoDB client and database instances."""

    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


db_instance = MongoDB()


async def connect_to_mongo():
    """Initialize MongoDB client, verify connection, and create indexes."""
    if os.environ.get("TESTING") == "1":
        logger.info("Skipping MongoDB connection in TESTING mode.")
        return

    if db_instance.client is not None:
        logger.info("MongoDB client already configured.")
        return

    mongodb_uri = settings.mongodb_uri.strip()

    # Validate MongoDB URI
    if not mongodb_uri.startswith(("mongodb://", "mongodb+srv://")):
        logger.error(
            "Invalid MongoDB URI scheme. "
            "Expected mongodb:// or mongodb+srv://."
        )
        return

    # Check placeholder credentials
    if "YOUR_PASSWORD" in mongodb_uri:
        logger.error(
            "MongoDB URI still contains placeholder credentials. "
            "Please configure the real password in Render Environment."
        )
        return

    if not mongodb_uri:
        logger.error("MONGODB_URI is empty.")
        return

    logger.info(
        "Initializing MongoDB connection to database: %s",
        settings.database_name,
    )

    try:
        client_kwargs = {
            "serverSelectionTimeoutMS": 5000,
            "connectTimeoutMS": 5000,
            "socketTimeoutMS": 10000,
            "retryWrites": True,
        }
        try:
            client_kwargs["tlsCAFile"] = certifi.where()
        except Exception:
            pass

        db_instance.client = AsyncIOMotorClient(mongodb_uri, **client_kwargs)
        db_instance.db = db_instance.client[settings.database_name]

        # Verify MongoDB Atlas connectivity with a non-blocking timeout
        # If ping times out or fails (e.g. IP whitelist 0.0.0.0/0 missing in Atlas),
        # log a warning but keep the client active so Motor can reconnect when ready.
        try:
            await asyncio.wait_for(
                db_instance.client.admin.command("ping"),
                timeout=3.0,
            )
            logger.info("Successfully connected to MongoDB Atlas!")
            await _create_indexes(db_instance.db)
        except Exception as ping_exc:
            logger.warning(
                "MongoDB Atlas ping check did not complete during startup (%s: %s). "
                "The web server is online. Please ensure '0.0.0.0/0' is whitelisted in MongoDB Atlas "
                "Network Access so Render can communicate with your database.",
                type(ping_exc).__name__,
                ping_exc,
            )

    except Exception as exc:
        logger.exception(
            "MongoDB client initialization failed: %s: %r",
            type(exc).__name__,
            exc,
        )


async def _create_indexes(db: AsyncIOMotorDatabase):
    """Creates performance and unique constraints on collections."""
    try:
        # Create unique indexes on users collection
        user_col = db["users"]
        await user_col.create_index([("email", ASCENDING)], unique=True, name="uniq_user_email")
        await user_col.create_index([("username", ASCENDING)], unique=True, name="uniq_user_username")
        await user_col.create_index([("full_name", ASCENDING)], name="idx_user_full_name")
        await user_col.create_index([("is_active", ASCENDING), ("username", ASCENDING)], name="idx_active_username")

        # Index follows collection
        follows_col = db["follows"]
        await follows_col.create_index([("follower_user_id", ASCENDING), ("following_user_id", ASCENDING)], unique=True, name="uniq_follow_relationship")
        await follows_col.create_index([("follower_user_id", ASCENDING)], name="idx_follower_user_id")
        await follows_col.create_index([("following_user_id", ASCENDING)], name="idx_following_user_id")

        # Index posts collection
        posts_col = db["posts"]
        await posts_col.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_posts_user_created")
        await posts_col.create_index([("created_at", DESCENDING)], name="idx_posts_created_at")

        # Index likes collection
        likes_col = db["likes"]
        await likes_col.create_index([("user_id", ASCENDING), ("post_id", ASCENDING)], unique=True, name="uniq_user_post_like")

        # Index comments collection
        comments_col = db["comments"]
        await comments_col.create_index([("post_id", ASCENDING), ("created_at", ASCENDING)], name="idx_comments_post_created")

        # Index saved_posts collection
        saved_col = db["saved_posts"]
        await saved_col.create_index([("user_id", ASCENDING), ("post_id", ASCENDING)], unique=True, name="uniq_user_saved_post")

        # Index conversations & messages
        convs_col = db["conversations"]
        await convs_col.create_index([("participant_ids", ASCENDING)], name="idx_conv_participants")
        await convs_col.create_index([("updated_at", DESCENDING)], name="idx_conv_updated_at")

        msgs_col = db["messages"]
        await msgs_col.create_index([("conversation_id", ASCENDING), ("created_at", ASCENDING)], name="idx_messages_conv_created")

        # Index notifications
        notif_col = db["notifications"]
        await notif_col.create_index([("recipient_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)], name="idx_notif_recipient_read")

        # Index blocks & reports
        blocks_col = db["blocks"]
        await blocks_col.create_index([("blocker_id", ASCENDING), ("blocked_id", ASCENDING)], unique=True, name="uniq_block_pair")

        logger.info("MongoDB indexes verified successfully.")
    except Exception as e:
        logger.warning("Index creation encountered error: %s", e)


async def close_mongo_connection():
    """Gracefully close MongoDB connection."""
    if os.environ.get("TESTING") == "1":
        return

    if db_instance.client is not None:
        try:
            db_instance.client.close()
            logger.info("MongoDB client connection closed.")
        except Exception:
            logger.exception("Error while closing MongoDB connection.")
        finally:
            db_instance.client = None
            db_instance.db = None


def get_database() -> Optional[AsyncIOMotorDatabase]:
    """Return the current MongoDB database instance."""

    return db_instance.db


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Generic collection getter."""
    if db_instance.db is None:
        raise RuntimeError(
            "Database connection has not been initialized. "
            "Please check MONGODB_URI in Render Environment."
        )
    return db_instance.db[name]


def get_user_collection() -> AsyncIOMotorCollection:
    """Return users collection."""
    return get_collection("users")


def get_follow_collection() -> AsyncIOMotorCollection:
    """Return follows collection."""
    return get_collection("follows")


def get_post_collection() -> AsyncIOMotorCollection:
    """Return posts collection."""
    return get_collection("posts")


def get_like_collection() -> AsyncIOMotorCollection:
    """Return likes collection."""
    return get_collection("likes")


def get_comment_collection() -> AsyncIOMotorCollection:
    """Return comments collection."""
    return get_collection("comments")


def get_saved_post_collection() -> AsyncIOMotorCollection:
    """Return saved_posts collection."""
    return get_collection("saved_posts")


def get_conversation_collection() -> AsyncIOMotorCollection:
    """Return conversations collection."""
    return get_collection("conversations")


def get_message_collection() -> AsyncIOMotorCollection:
    """Return messages collection."""
    return get_collection("messages")


def get_notification_collection() -> AsyncIOMotorCollection:
    """Return notifications collection."""
    return get_collection("notifications")


def get_block_collection() -> AsyncIOMotorCollection:
    """Return blocks collection."""
    return get_collection("blocks")


def get_report_collection() -> AsyncIOMotorCollection:
    """Return reports collection."""
    return get_collection("reports")
