import re
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorCollection

from app.database.mongodb import get_user_collection
from app.schemas.user import (
    PaginationMetadata,
    UserSearchResponse,
    UserSearchResult,
)


class UserService:
    """Handles user search, user discovery, and public profile retrieval."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        self._col = collection

    @property
    def col(self) -> AsyncIOMotorCollection:
        if self._col is not None:
            return self._col
        return get_user_collection()

    async def search_users(
        self,
        query: str,
        current_user_id: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> UserSearchResponse:
        """
        Searches users collection by username or full_name with case-insensitive partial matching.
        Excludes the currently authenticated user and strictly projects only public fields.
        """
        clean = query.strip()
        if clean.startswith("@"):
            clean = clean[1:].strip()

        # Normalize pagination parameters
        page = max(1, page)
        limit = min(max(1, limit), 50)
        skip = (page - 1) * limit

        if not clean:
            return UserSearchResponse(
                success=True,
                users=[],
                pagination=PaginationMetadata(
                    page=page,
                    limit=limit,
                    total=0,
                    has_more=False,
                ),
            )

        collection = self.col

        # Escape user input to prevent regex injection or ReDoS
        escaped_query = re.escape(clean)
        regex_filter = {"$regex": escaped_query, "$options": "i"}

        # Build compound search filter
        and_conditions = [
            {"is_active": {"$ne": False}},
            {
                "$or": [
                    {"username": regex_filter},
                    {"full_name": regex_filter},
                ]
            },
        ]

        # Exclude currently authenticated user from search results
        if current_user_id:
            and_conditions.append({"id": {"$ne": current_user_id}})

        filter_query = {"$and": and_conditions}

        # Count total matching documents
        total = await collection.count_documents(filter_query)

        # Explicit projection: ONLY public fields, NEVER passwords, hashes, emails, or phones
        projection = {
            "_id": 0,
            "id": 1,
            "username": 1,
            "full_name": 1,
            "profile_picture": 1,
            "avatar_url": 1,
            "bio": 1,
            "is_verified": 1,
            "followers_count": 1,
            "following_count": 1,
        }

        cursor = (
            collection.find(filter_query, projection)
            .sort("username", 1)
            .skip(skip)
            .limit(limit)
        )

        user_docs = await cursor.to_list(length=limit)

        users: List[UserSearchResult] = []
        for doc in user_docs:
            pic = doc.get("profile_picture") or doc.get("avatar_url") or ""
            users.append(
                UserSearchResult(
                    id=str(doc.get("id", "")),
                    username=str(doc.get("username", "")),
                    full_name=str(doc.get("full_name", "")),
                    profile_picture=pic,
                    avatar_url=pic,
                    bio=str(doc.get("bio") or ""),
                    is_verified=bool(doc.get("is_verified", False)),
                    followers_count=int(doc.get("followers_count", 0)),
                    following_count=int(doc.get("following_count", 0)),
                )
            )

        has_more = (skip + len(users)) < total

        return UserSearchResponse(
            success=True,
            users=users,
            pagination=PaginationMetadata(
                page=page,
                limit=limit,
                total=total,
                has_more=has_more,
            ),
        )

    async def get_user_by_id(self, user_id: str) -> Optional[UserSearchResult]:
        """
        Retrieves public profile of a user by UUID identifier.
        Never returns private or sensitive credentials.
        """
        collection = self.col
        projection = {
            "_id": 0,
            "id": 1,
            "username": 1,
            "full_name": 1,
            "profile_picture": 1,
            "avatar_url": 1,
            "bio": 1,
            "is_verified": 1,
            "followers_count": 1,
            "following_count": 1,
        }
        doc = await collection.find_one({"id": user_id, "is_active": {"$ne": False}}, projection)
        if not doc:
            return None

        pic = doc.get("profile_picture") or doc.get("avatar_url") or ""
        return UserSearchResult(
            id=str(doc.get("id", "")),
            username=str(doc.get("username", "")),
            full_name=str(doc.get("full_name", "")),
            profile_picture=pic,
            avatar_url=pic,
            bio=str(doc.get("bio") or ""),
            is_verified=bool(doc.get("is_verified", False)),
            followers_count=int(doc.get("followers_count", 0)),
            following_count=int(doc.get("following_count", 0)),
        )


user_service = UserService()
