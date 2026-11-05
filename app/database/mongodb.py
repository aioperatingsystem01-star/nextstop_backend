
import asyncio
import logging
from typing import Optional

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection,
)
from pymongo import ASCENDING

from app.core.config import settings

logger = logging.getLogger("nextstop.database")


class MongoDB:
    """Singleton holder for MongoDB client and database instances."""

    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


db_instance = MongoDB()


async def connect_to_mongo():
    """Initialize MongoDB client, verify connection, and create indexes."""

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
        db_instance.client = AsyncIOMotorClient(
            mongodb_uri,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
            retryWrites=True,
            tls=True,
        )

        db_instance.db = db_instance.client[settings.database_name]

        # Verify MongoDB Atlas connectivity
        await asyncio.wait_for(
            db_instance.client.admin.command("ping"),
            timeout=15.0,
        )

        logger.info("Successfully connected to MongoDB Atlas!")

        # Create unique indexes on users collection
        user_col = db_instance.db["users"]

        await user_col.create_index(
            [("email", ASCENDING)],
            unique=True,
            name="uniq_user_email",
        )

        await user_col.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="uniq_user_username",
        )

        await user_col.create_index(
            [("full_name", ASCENDING)],
            name="idx_user_full_name",
        )

        await user_col.create_index(
            [("is_active", ASCENDING), ("username", ASCENDING)],
            name="idx_active_username",
        )

        logger.info(
            "Indexes on 'email', 'username', and 'full_name' verified successfully."
        )

    except Exception as exc:
        logger.exception(
            "MongoDB Atlas connection failed. "
            "Error type: %s, Details: %r",
            type(exc).__name__,
            exc,
        )

        # Clean up failed connection
        if db_instance.client is not None:
            db_instance.client.close()

        db_instance.client = None
        db_instance.db = None


async def close_mongo_connection():
    """Gracefully close MongoDB connection."""

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


def get_user_collection() -> AsyncIOMotorCollection:
    """Return users collection."""

    if db_instance.db is None:
        raise RuntimeError(
            "Database connection has not been initialized. "
            "Please check MONGODB_URI in Render Environment."
        )

    return db_instance.db["users"]
