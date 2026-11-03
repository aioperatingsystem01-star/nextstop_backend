import asyncio
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ASCENDING

from app.core.config import settings

logger = logging.getLogger("nextstop.database")


class MongoDB:
    """Singleton holder for MongoDB client and database instances."""
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


db_instance = MongoDB()


async def connect_to_mongo():
    """Initializes MongoDB client, pings server, and ensures unique indexes."""
    # If client is already set (e.g., mock client during testing), skip
    if db_instance.client is not None:
        logger.info("MongoDB client already configured.")
        return

    # Check for placeholder credentials in .env
    if "YOUR_PASSWORD" in settings.mongodb_uri:
        logger.warning(
            "MONGODB_URI in .env contains placeholder 'YOUR_PASSWORD'. "
            "Database operations will be active as soon as you update .env with your real MongoDB Atlas password."
        )
        return

    logger.info("Initializing MongoDB connection to %s...", settings.database_name)
    try:
        db_instance.client = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        db_instance.db = db_instance.client[settings.database_name]

        # Verify connectivity with timeout
        await asyncio.wait_for(db_instance.client.admin.command("ping"), timeout=3.0)
        logger.info("Successfully connected to MongoDB Atlas!")

        # Create unique indexes on users collection
        user_col = db_instance.db["users"]
        await user_col.create_index([("email", ASCENDING)], unique=True, name="uniq_user_email")
        await user_col.create_index([("username", ASCENDING)], unique=True, name="uniq_user_username")
        logger.info("Unique indexes on 'email' and 'username' verified successfully.")
    except Exception as exc:
        logger.warning(
            "MongoDB Atlas connection check warning: %s. "
            "Ensure MONGODB_URI in .env contains valid cluster credentials.",
            exc,
        )


async def close_mongo_connection():
    """Gracefully closes MongoDB client connection."""
    if db_instance.client is not None:
        try:
            db_instance.client.close()
            logger.info("MongoDB client connection closed.")
        except Exception:
            pass


def get_database() -> Optional[AsyncIOMotorDatabase]:
    """Returns the current MongoDB database instance."""
    return db_instance.db


def get_user_collection() -> AsyncIOMotorCollection:
    """Returns the users collection. Raises RuntimeError if database is not initialized."""
    if db_instance.db is None:
        raise RuntimeError(
            "Database connection has not been initialized. "
            "Please check MONGODB_URI in your .env file."
        )
    return db_instance.db["users"]
