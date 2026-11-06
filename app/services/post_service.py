from datetime import datetime, timezone
import re
from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.database.mongodb import (
    get_comment_collection,
    get_follow_collection,
    get_like_collection,
    get_post_collection,
    get_saved_post_collection,
    get_user_collection,
)
from app.models.post import CommentModel, LikeModel, PostModel, SavedPostModel
from app.schemas.post import (
    CommentResponse,
    LikeToggleResponse,
    PostResponse,
    PostsListResponse,
    SaveToggleResponse,
)
from app.services.notification_service import notification_service


class PostService:
    """Manages posts, feeds, likes, comments, and bookmarks in MongoDB."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        self._col = collection

    @property
    def col(self) -> AsyncIOMotorCollection:
        if self._col is not None:
            return self._col
        return get_post_collection()

    async def create_post(
        self,
        user_id: str,
        caption: str,
        hashtags: List[str],
        media_url: str,
        media_type: str = "image",
    ) -> PostResponse:
        """Publishes a new post and increments the creator's posts_count."""
        # Auto-extract hashtags if none provided
        clean_tags = list(hashtags)
        if not clean_tags and caption:
            found = re.findall(r"#(\w+)", caption)
            clean_tags = [f"#{t.lower()}" for t in found]

        now = datetime.now(timezone.utc)
        post_id = f"post_{uuid.uuid4().hex[:12]}"
        post = PostModel(
            id=post_id,
            user_id=user_id,
            caption=caption.strip(),
            hashtags=clean_tags,
            media_urls=[media_url],
            media_type=media_type,
            likes_count=0,
            comments_count=0,
            created_at=now,
            updated_at=now,
        )

        await self.col.insert_one(post.model_dump())

        # Atomically increment user's posts_count
        user_col = get_user_collection()
        user = await user_col.find_one_and_update(
            {"id": user_id},
            {"$inc": {"posts_count": 1}},
            return_document=True,
        )

        pic = user.get("profile_picture") or user.get("avatar_url") or "" if user else ""
        return PostResponse(
            id=post_id,
            user_id=user_id,
            username=user.get("username", "") if user else "",
            full_name=user.get("full_name", "") if user else "",
            user_avatar=pic,
            caption=post.caption,
            hashtags=post.hashtags,
            media_urls=post.media_urls,
            media_type=post.media_type,
            likes_count=0,
            comments_count=0,
            is_liked=False,
            is_saved=False,
            created_at=now,
        )

    async def delete_post(self, post_id: str, user_id: str) -> bool:
        """Deletes a post verifying user ownership."""
        post = await self.col.find_one({"id": post_id})
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

        if post["user_id"] != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete other user's post.")

        await self.col.delete_one({"id": post_id})

        # Decrement posts_count
        user_col = get_user_collection()
        await user_col.update_one({"id": user_id, "posts_count": {"$gt": 0}}, {"$inc": {"posts_count": -1}})

        # Clean up likes, comments, and saves
        await get_like_collection().delete_many({"post_id": post_id})
        await get_comment_collection().delete_many({"post_id": post_id})
        await get_saved_post_collection().delete_many({"post_id": post_id})
        return True

    async def get_user_posts(
        self,
        target_user_id: str,
        current_user_id: Optional[str] = None,
        page: int = 1,
        limit: int = 24,
    ) -> PostsListResponse:
        """Fetches posts published by target_user_id for Profile Content Tabs."""
        skip = (page - 1) * limit
        cursor = self.col.find({"user_id": target_user_id}).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        total = await self.col.count_documents({"user_id": target_user_id})

        posts = await self._hydrate_posts(docs, current_user_id)
        has_more = (skip + len(docs)) < total
        return PostsListResponse(success=True, posts=posts, total=total, has_more=has_more)

    async def get_explore_feed(
        self,
        current_user_id: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> PostsListResponse:
        """Fetches public discovery feed."""
        skip = (page - 1) * limit
        cursor = self.col.find().sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        total = await self.col.count_documents({})

        posts = await self._hydrate_posts(docs, current_user_id)
        has_more = (skip + len(docs)) < total
        return PostsListResponse(success=True, posts=posts, total=total, has_more=has_more)

    async def get_following_feed(
        self,
        current_user_id: str,
        page: int = 1,
        limit: int = 20,
    ) -> PostsListResponse:
        """Fetches feed composed of posts from accounts the user follows."""
        follows_col = get_follow_collection()
        follow_docs = await follows_col.find({"follower_user_id": current_user_id}).to_list(length=500)
        following_ids = [f["following_user_id"] for f in follow_docs]
        following_ids.append(current_user_id)  # Include own posts

        skip = (page - 1) * limit
        filter_query = {"user_id": {"$in": following_ids}}
        cursor = self.col.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        total = await self.col.count_documents(filter_query)

        posts = await self._hydrate_posts(docs, current_user_id)
        has_more = (skip + len(docs)) < total
        return PostsListResponse(success=True, posts=posts, total=total, has_more=has_more)

    async def toggle_like(self, post_id: str, user_id: str) -> LikeToggleResponse:
        """Likes or unlikes a post atomically and triggers like notification."""
        post = await self.col.find_one({"id": post_id})
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

        likes_col = get_like_collection()
        existing = await likes_col.find_one({"post_id": post_id, "user_id": user_id})

        if existing:
            # Unlike
            await likes_col.delete_one({"id": existing["id"]})
            updated = await self.col.find_one_and_update(
                {"id": post_id, "likes_count": {"$gt": 0}},
                {"$inc": {"likes_count": -1}},
                return_document=True,
            )
            count = updated.get("likes_count", 0) if updated else 0
            return LikeToggleResponse(success=True, post_id=post_id, is_liked=False, likes_count=count)
        else:
            # Like
            like_id = f"like_{uuid.uuid4().hex[:12]}"
            await likes_col.insert_one(
                LikeModel(id=like_id, user_id=user_id, post_id=post_id).model_dump()
            )
            updated = await self.col.find_one_and_update(
                {"id": post_id},
                {"$inc": {"likes_count": 1}},
                return_document=True,
            )
            count = updated.get("likes_count", 1) if updated else 1

            # Notify creator
            creator_id = post["user_id"]
            if creator_id != user_id:
                user_col = get_user_collection()
                u = await user_col.find_one({"id": user_id})
                liker_name = u.get("full_name") or u.get("username") if u else "Someone"
                await notification_service.create_notification(
                    recipient_id=creator_id,
                    actor_id=user_id,
                    type="post_like",
                    title="New Like",
                    body=f"{liker_name} liked your photo post.",
                    entity_id=post_id,
                )

            return LikeToggleResponse(success=True, post_id=post_id, is_liked=True, likes_count=count)

    async def add_comment(self, post_id: str, user_id: str, text: str) -> CommentResponse:
        """Adds a comment to a post and notifies the post creator."""
        post = await self.col.find_one({"id": post_id})
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

        now = datetime.now(timezone.utc)
        comment_id = f"cmt_{uuid.uuid4().hex[:12]}"
        cmt = CommentModel(
            id=comment_id,
            post_id=post_id,
            user_id=user_id,
            text=text.strip(),
            created_at=now,
        )

        await get_comment_collection().insert_one(cmt.model_dump())
        await self.col.update_one({"id": post_id}, {"$inc": {"comments_count": 1}})

        user_col = get_user_collection()
        author = await user_col.find_one({"id": user_id})
        author_name = author.get("full_name") or author.get("username") if author else "Someone"
        pic = author.get("profile_picture") or author.get("avatar_url") or "" if author else ""

        # Notify post creator
        if post["user_id"] != user_id:
            await notification_service.create_notification(
                recipient_id=post["user_id"],
                actor_id=user_id,
                type="post_comment",
                title="New Comment",
                body=f"{author_name} commented: \"{text[:40]}\"",
                entity_id=post_id,
            )

        return CommentResponse(
            id=comment_id,
            post_id=post_id,
            user_id=user_id,
            username=author.get("username", "") if author else "",
            full_name=author.get("full_name", "") if author else "",
            user_avatar=pic,
            text=cmt.text,
            created_at=now,
        )

    async def get_comments(self, post_id: str) -> List[CommentResponse]:
        """Returns comments for a post in chronological order."""
        comments_col = get_comment_collection()
        docs = await comments_col.find({"post_id": post_id}).sort("created_at", 1).to_list(length=100)
        user_ids = list({d["user_id"] for d in docs})

        user_col = get_user_collection()
        user_map = {}
        if user_ids:
            u_docs = await user_col.find({"id": {"$in": user_ids}}).to_list(length=len(user_ids))
            for u in u_docs:
                user_map[u["id"]] = u

        results: List[CommentResponse] = []
        for d in docs:
            u = user_map.get(d["user_id"])
            pic = u.get("profile_picture") or u.get("avatar_url") or "" if u else ""
            results.append(
                CommentResponse(
                    id=d["id"],
                    post_id=post_id,
                    user_id=d["user_id"],
                    username=u.get("username", "") if u else "",
                    full_name=u.get("full_name", "") if u else "",
                    user_avatar=pic,
                    text=d["text"],
                    created_at=d.get("created_at", datetime.now(timezone.utc)),
                )
            )
        return results

    async def toggle_save(self, post_id: str, user_id: str) -> SaveToggleResponse:
        """Saves or unsaves a post for the authenticated user."""
        saved_col = get_saved_post_collection()
        existing = await saved_col.find_one({"post_id": post_id, "user_id": user_id})

        if existing:
            await saved_col.delete_one({"id": existing["id"]})
            return SaveToggleResponse(success=True, post_id=post_id, is_saved=False)
        else:
            await saved_col.insert_one(
                SavedPostModel(
                    id=f"save_{uuid.uuid4().hex[:12]}",
                    user_id=user_id,
                    post_id=post_id,
                ).model_dump()
            )
            return SaveToggleResponse(success=True, post_id=post_id, is_saved=True)

    async def get_saved_posts(self, user_id: str, page: int = 1, limit: int = 24) -> PostsListResponse:
        """Fetches posts saved by user for the Saved content tab."""
        saved_col = get_saved_post_collection()
        skip = (page - 1) * limit
        cursor = saved_col.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
        saved_records = await cursor.to_list(length=limit)
        total = await saved_col.count_documents({"user_id": user_id})

        post_ids = [r["post_id"] for r in saved_records]
        if not post_ids:
            return PostsListResponse(success=True, posts=[], total=0, has_more=False)

        posts_cursor = self.col.find({"id": {"$in": post_ids}})
        docs = await posts_cursor.to_list(length=len(post_ids))
        docs_map = {d["id"]: d for d in docs}
        ordered_docs = [docs_map[pid] for pid in post_ids if pid in docs_map]

        posts = await self._hydrate_posts(ordered_docs, user_id)
        has_more = (skip + len(saved_records)) < total
        return PostsListResponse(success=True, posts=posts, total=total, has_more=has_more)

    async def _hydrate_posts(self, docs: List[dict], current_user_id: Optional[str] = None) -> List[PostResponse]:
        if not docs:
            return []

        post_ids = [d["id"] for d in docs]
        creator_ids = list({d["user_id"] for d in docs})

        # Fetch authors
        user_col = get_user_collection()
        creators = await user_col.find({"id": {"$in": creator_ids}}).to_list(length=len(creator_ids))
        author_map = {c["id"]: c for c in creators}

        # Check likes and saved for current_user_id
        liked_set = set()
        saved_set = set()
        if current_user_id:
            likes = await get_like_collection().find(
                {"post_id": {"$in": post_ids}, "user_id": current_user_id}
            ).to_list(length=len(post_ids))
            liked_set = {l["post_id"] for l in likes}

            saves = await get_saved_post_collection().find(
                {"post_id": {"$in": post_ids}, "user_id": current_user_id}
            ).to_list(length=len(post_ids))
            saved_set = {s["post_id"] for s in saves}

        results: List[PostResponse] = []
        for d in docs:
            author = author_map.get(d.get("user_id"))
            pic = author.get("profile_picture") or author.get("avatar_url") or "" if author else ""
            pid = d["id"]

            results.append(
                PostResponse(
                    id=pid,
                    user_id=d.get("user_id", ""),
                    username=author.get("username", "") if author else "creator",
                    full_name=author.get("full_name", "") if author else "Creator",
                    user_avatar=pic,
                    caption=d.get("caption", ""),
                    hashtags=d.get("hashtags", []),
                    media_urls=d.get("media_urls", []),
                    media_type=d.get("media_type", "image"),
                    likes_count=int(d.get("likes_count", 0)),
                    comments_count=int(d.get("comments_count", 0)),
                    is_liked=pid in liked_set,
                    is_saved=pid in saved_set,
                    created_at=d.get("created_at", datetime.now(timezone.utc)),
                )
            )
        return results


post_service = PostService()
