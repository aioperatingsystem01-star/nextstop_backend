from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.database.mongodb import get_follow_collection, get_user_collection
from app.models.follow import FollowModel
from app.schemas.user import (
    FollowActionResponse,
    FollowersListResponse,
    UserRelationshipResponse,
    UserSearchResult,
)
from app.services.notification_service import notification_service


class FollowService:
    """Manages user relationships, follower/following counts, and social notifications."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        self._col = collection

    @property
    def col(self) -> AsyncIOMotorCollection:
        if self._col is not None:
            return self._col
        return get_follow_collection()

    async def get_relationship(self, current_user_id: str, target_user_id: str) -> UserRelationshipResponse:
        """Determines relationship status between current user and target user."""
        if current_user_id == target_user_id:
            return UserRelationshipResponse(
                target_user_id=target_user_id,
                is_following=False,
                is_followed_by=False,
                follow_status="self",
            )

        follows_col = self.col
        # Does current user follow target?
        is_following_doc = await follows_col.find_one({
            "follower_user_id": current_user_id,
            "following_user_id": target_user_id,
        })
        is_following = is_following_doc is not None

        # Does target user follow current user?
        is_followed_by_doc = await follows_col.find_one({
            "follower_user_id": target_user_id,
            "following_user_id": current_user_id,
        })
        is_followed_by = is_followed_by_doc is not None

        if is_following:
            follow_status = "following"
        elif is_followed_by:
            follow_status = "follow_back"
        else:
            follow_status = "follow"

        return UserRelationshipResponse(
            target_user_id=target_user_id,
            is_following=is_following,
            is_followed_by=is_followed_by,
            follow_status=follow_status,
        )

    async def follow_user(self, current_user_id: str, target_user_id: str) -> FollowActionResponse:
        """Executes a follow action, updates database counts atomically, and triggers notification."""
        if current_user_id == target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot follow your own account.",
            )

        user_col = get_user_collection()
        target_user = await user_col.find_one({"id": target_user_id, "is_active": {"$ne": False}})
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        current_user = await user_col.find_one({"id": current_user_id})
        current_user_name = current_user.get("full_name") or current_user.get("username") if current_user else "Someone"

        follows_col = self.col
        # Check if already following
        existing = await follows_col.find_one({
            "follower_user_id": current_user_id,
            "following_user_id": target_user_id,
        })

        if existing:
            # Already following - return current state safely
            return FollowActionResponse(
                success=True,
                message="Already following.",
                follow_status="following",
                target_followers_count=target_user.get("followers_count", 0),
                user_following_count=current_user.get("following_count", 0) if current_user else 0,
            )

        # Check if target user follows current user (to trigger Follow Back notification)
        follows_back = await follows_col.find_one({
            "follower_user_id": target_user_id,
            "following_user_id": current_user_id,
        })

        now = datetime.now(timezone.utc)
        follow_record = FollowModel(
            id=f"flw_{uuid.uuid4().hex[:12]}",
            follower_user_id=current_user_id,
            following_user_id=target_user_id,
            created_at=now,
        )

        await follows_col.insert_one(follow_record.model_dump())

        # Atomic counter updates
        updated_target = await user_col.find_one_and_update(
            {"id": target_user_id},
            {"$inc": {"followers_count": 1}},
            return_document=True,
        )
        updated_current = await user_col.find_one_and_update(
            {"id": current_user_id},
            {"$inc": {"following_count": 1}},
            return_document=True,
        )

        target_followers = updated_target.get("followers_count", 1) if updated_target else 1
        user_following = updated_current.get("following_count", 1) if updated_current else 1

        # Dispatch notification
        if follows_back:
            await notification_service.create_notification(
                recipient_id=target_user_id,
                actor_id=current_user_id,
                type="follow_back",
                title="Follow Back",
                body=f"{current_user_name} followed you back.",
                entity_id=current_user_id,
            )
        else:
            await notification_service.create_notification(
                recipient_id=target_user_id,
                actor_id=current_user_id,
                type="new_follower",
                title="New Follower",
                body=f"{current_user_name} started following you.",
                entity_id=current_user_id,
            )

        return FollowActionResponse(
            success=True,
            message="Successfully followed user.",
            follow_status="following",
            target_followers_count=target_followers,
            user_following_count=user_following,
        )

    async def unfollow_user(self, current_user_id: str, target_user_id: str) -> FollowActionResponse:
        """Executes an unfollow action and decrements counters atomically."""
        if current_user_id == target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot unfollow yourself.",
            )

        follows_col = self.col
        res = await follows_col.delete_one({
            "follower_user_id": current_user_id,
            "following_user_id": target_user_id,
        })

        user_col = get_user_collection()
        if res.deleted_count > 0:
            # Decrement atomically (preventing negatives)
            updated_target = await user_col.find_one_and_update(
                {"id": target_user_id, "followers_count": {"$gt": 0}},
                {"$inc": {"followers_count": -1}},
                return_document=True,
            )
            updated_current = await user_col.find_one_and_update(
                {"id": current_user_id, "following_count": {"$gt": 0}},
                {"$inc": {"following_count": -1}},
                return_document=True,
            )
            target_followers = updated_target.get("followers_count", 0) if updated_target else 0
            user_following = updated_current.get("following_count", 0) if updated_current else 0
        else:
            t = await user_col.find_one({"id": target_user_id}) or {}
            c = await user_col.find_one({"id": current_user_id}) or {}
            target_followers = t.get("followers_count", 0)
            user_following = c.get("following_count", 0)

        # Check if target follows current user
        target_follows_me = await follows_col.find_one({
            "follower_user_id": target_user_id,
            "following_user_id": current_user_id,
        })
        next_status = "follow_back" if target_follows_me else "follow"

        return FollowActionResponse(
            success=True,
            message="Successfully unfollowed user.",
            follow_status=next_status,
            target_followers_count=target_followers,
            user_following_count=user_following,
        )

    async def get_followers(self, target_user_id: str, current_user_id: Optional[str] = None) -> FollowersListResponse:
        """Retrieves list of users following target_user_id."""
        cursor = self.col.find({"following_user_id": target_user_id}).sort("created_at", -1)
        records = await cursor.to_list(length=100)
        follower_ids = [r["follower_user_id"] for r in records]

        users = await self._hydrate_users(follower_ids, current_user_id)
        return FollowersListResponse(success=True, users=users, total=len(users))

    async def get_following(self, target_user_id: str, current_user_id: Optional[str] = None) -> FollowersListResponse:
        """Retrieves list of users target_user_id is following."""
        cursor = self.col.find({"follower_user_id": target_user_id}).sort("created_at", -1)
        records = await cursor.to_list(length=100)
        following_ids = [r["following_user_id"] for r in records]

        users = await self._hydrate_users(following_ids, current_user_id)
        return FollowersListResponse(success=True, users=users, total=len(users))

    async def _hydrate_users(self, user_ids: List[str], current_user_id: Optional[str] = None) -> List[UserSearchResult]:
        if not user_ids:
            return []
        user_col = get_user_collection()
        docs = await user_col.find(
            {"id": {"$in": user_ids}, "is_active": {"$ne": False}},
            {
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
            },
        ).to_list(length=len(user_ids))

        # Check follow status for each from perspective of current_user_id
        my_following_set = set()
        they_follow_me_set = set()
        if current_user_id:
            cursor1 = self.col.find({"follower_user_id": current_user_id, "following_user_id": {"$in": user_ids}})
            for r in await cursor1.to_list(length=len(user_ids)):
                my_following_set.add(r["following_user_id"])

            cursor2 = self.col.find({"follower_user_id": {"$in": user_ids}, "following_user_id": current_user_id})
            for r in await cursor2.to_list(length=len(user_ids)):
                they_follow_me_set.add(r["follower_user_id"])

        results: List[UserSearchResult] = []
        for d in docs:
            uid = d["id"]
            pic = d.get("profile_picture") or d.get("avatar_url") or ""
            is_following = uid in my_following_set
            is_followed_by = uid in they_follow_me_set

            if uid == current_user_id:
                follow_status = "self"
            elif is_following:
                follow_status = "following"
            elif is_followed_by:
                follow_status = "follow_back"
            else:
                follow_status = "follow"

            results.append(
                UserSearchResult(
                    id=uid,
                    username=d.get("username", ""),
                    full_name=d.get("full_name", ""),
                    profile_picture=pic,
                    avatar_url=pic,
                    bio=d.get("bio", ""),
                    website=d.get("website", ""),
                    is_verified=bool(d.get("is_verified", False)),
                    followers_count=int(d.get("followers_count", 0)),
                    following_count=int(d.get("following_count", 0)),
                    posts_count=int(d.get("posts_count", 0)),
                    is_following=is_following,
                    is_followed_by=is_followed_by,
                    follow_status=follow_status,
                )
            )
        return results


follow_service = FollowService()
