import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.database.mongodb import (
    get_block_collection,
    get_follow_collection,
    get_report_collection,
    get_user_collection,
)
from app.models.safety import BlockModel, ReportModel
from app.schemas.auth import UserProfileResponse
from app.schemas.safety import BlockResponse, ReportResponse
from app.schemas.user import (
    PaginationMetadata,
    UserSearchResponse,
    UserSearchResult,
    UserUpdateProfileRequest,
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

    async def get_user_by_id(
        self,
        user_id: str,
        current_user_id: Optional[str] = None,
    ) -> Optional[UserSearchResult]:
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
            "website": 1,
            "is_verified": 1,
            "followers_count": 1,
            "following_count": 1,
            "posts_count": 1,
        }
        doc = await collection.find_one({"id": user_id, "is_active": {"$ne": False}}, projection)
        if not doc:
            return None

        # Check follow relationship
        is_following = False
        is_followed_by = False
        follow_status_val = "follow"

        if current_user_id and current_user_id != user_id:
            follows_col = get_follow_collection()
            is_following = await follows_col.find_one({
                "follower_user_id": current_user_id,
                "following_user_id": user_id,
            }) is not None

            is_followed_by = await follows_col.find_one({
                "follower_user_id": user_id,
                "following_user_id": current_user_id,
            }) is not None

            if is_following:
                follow_status_val = "following"
            elif is_followed_by:
                follow_status_val = "follow_back"
            else:
                follow_status_val = "follow"
        elif current_user_id == user_id:
            follow_status_val = "self"

        pic = doc.get("profile_picture") or doc.get("avatar_url") or ""
        return UserSearchResult(
            id=str(doc.get("id", "")),
            username=str(doc.get("username", "")),
            full_name=str(doc.get("full_name", "")),
            profile_picture=pic,
            avatar_url=pic,
            bio=str(doc.get("bio") or ""),
            website=str(doc.get("website") or ""),
            is_verified=bool(doc.get("is_verified", False)),
            followers_count=int(doc.get("followers_count", 0)),
            following_count=int(doc.get("following_count", 0)),
            posts_count=int(doc.get("posts_count", 0)),
            is_following=is_following,
            is_followed_by=is_followed_by,
            follow_status=follow_status_val,
        )

    async def update_profile(
        self,
        user_id: str,
        data: UserUpdateProfileRequest,
    ) -> UserProfileResponse:
        """Updates user's profile information ensuring username uniqueness if changed."""
        collection = self.col
        update_fields = {"updated_at": datetime.now(timezone.utc)}

        if data.full_name is not None:
            update_fields["full_name"] = data.full_name.strip()

        if data.bio is not None:
            update_fields["bio"] = data.bio.strip()

        if data.website is not None:
            update_fields["website"] = data.website.strip()

        if data.profile_picture is not None:
            update_fields["profile_picture"] = data.profile_picture.strip()
            update_fields["avatar_url"] = data.profile_picture.strip()
        elif data.avatar_url is not None:
            update_fields["profile_picture"] = data.avatar_url.strip()
            update_fields["avatar_url"] = data.avatar_url.strip()

        if data.username is not None:
            clean_username = data.username.strip().lower()
            existing = await collection.find_one({
                "username": clean_username,
                "id": {"$ne": user_id},
            })
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Username '@{clean_username}' is already taken.",
                )
            update_fields["username"] = clean_username

        updated = await collection.find_one_and_update(
            {"id": user_id},
            {"$set": update_fields},
            return_document=True,
        )

        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        pic = updated.get("profile_picture") or updated.get("avatar_url") or ""
        return UserProfileResponse(
            id=updated["id"],
            full_name=updated["full_name"],
            username=updated["username"],
            email=updated["email"],
            mobile_number=updated.get("mobile_number", ""),
            created_at=updated.get("created_at", datetime.now(timezone.utc)),
            profile_picture=pic,
            avatar_url=pic,
            bio=updated.get("bio", ""),
            website=updated.get("website", ""),
            is_verified=bool(updated.get("is_verified", False)),
            followers_count=int(updated.get("followers_count", 0)),
            following_count=int(updated.get("following_count", 0)),
            posts_count=int(updated.get("posts_count", 0)),
        )

    async def update_avatar(self, user_id: str, avatar_url: str) -> UserProfileResponse:
        """Updates user profile avatar URL."""
        collection = self.col
        updated = await collection.find_one_and_update(
            {"id": user_id},
            {
                "$set": {
                    "profile_picture": avatar_url,
                    "avatar_url": avatar_url,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=True,
        )

        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        return UserProfileResponse(
            id=updated["id"],
            full_name=updated["full_name"],
            username=updated["username"],
            email=updated["email"],
            mobile_number=updated.get("mobile_number", ""),
            created_at=updated.get("created_at", datetime.now(timezone.utc)),
            profile_picture=avatar_url,
            avatar_url=avatar_url,
            bio=updated.get("bio", ""),
            website=updated.get("website", ""),
            is_verified=bool(updated.get("is_verified", False)),
            followers_count=int(updated.get("followers_count", 0)),
            following_count=int(updated.get("following_count", 0)),
            posts_count=int(updated.get("posts_count", 0)),
        )

    async def block_user(self, blocker_id: str, blocked_id: str) -> BlockResponse:
        """Blocks a user and dissolves any follow relationship."""
        if blocker_id == blocked_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block yourself.")

        blocks_col = get_block_collection()
        existing = await blocks_col.find_one({"blocker_id": blocker_id, "blocked_id": blocked_id})
        if not existing:
            await blocks_col.insert_one(
                BlockModel(
                    id=f"blk_{uuid.uuid4().hex[:12]}",
                    blocker_id=blocker_id,
                    blocked_id=blocked_id,
                ).model_dump()
            )

        # Remove any follow relationship between them
        follows_col = get_follow_collection()
        await follows_col.delete_many({
            "$or": [
                {"follower_user_id": blocker_id, "following_user_id": blocked_id},
                {"follower_user_id": blocked_id, "following_user_id": blocker_id},
            ]
        })

        return BlockResponse(
            success=True,
            blocked_user_id=blocked_id,
            is_blocked=True,
            message="User has been blocked.",
        )

    async def unblock_user(self, blocker_id: str, blocked_id: str) -> BlockResponse:
        """Unblocks a user."""
        blocks_col = get_block_collection()
        await blocks_col.delete_one({"blocker_id": blocker_id, "blocked_id": blocked_id})
        return BlockResponse(
            success=True,
            blocked_user_id=blocked_id,
            is_blocked=False,
            message="User has been unblocked.",
        )

    async def create_report(
        self,
        reporter_id: str,
        target_id: str,
        target_type: str,
        reason: str,
    ) -> ReportResponse:
        """Submits a safety report."""
        report = ReportModel(
            id=f"rep_{uuid.uuid4().hex[:12]}",
            reporter_id=reporter_id,
            target_id=target_id,
            target_type=target_type,
            reason=reason.strip(),
        )
        await get_report_collection().insert_one(report.model_dump())
        return ReportResponse(
            success=True,
            report_id=report.id,
            message="Report received and registered securely.",
        )


user_service = UserService()
