# ==============================================================================
# NEXT STOP BACKEND - AUTHENTICATION SERVICE
# Updated: 2026-11-09 | Profile field initialization defaults & safe dict access
# ==============================================================================
from datetime import datetime, timezone
import uuid
from typing import Optional
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

import jwt
from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.database.mongodb import get_user_collection
from app.schemas.auth import SignUpRequest, LoginRequest, TokenResponse, UserProfileResponse


class AuthService:
    """Handles core business logic for user registration, authentication, and profiles."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        self._col = collection

    @property
    def col(self) -> AsyncIOMotorCollection:
        if self._col is not None:
            return self._col
        return get_user_collection()

    async def register_user(self, data: SignUpRequest) -> TokenResponse:
        """Registers a new user, hashes password with Argon2, saves to MongoDB, returns JWT and profile."""
        collection = self.col

        # Check duplicate email
        existing_email = await collection.find_one({"email": data.email})
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists.",
            )

        # Check duplicate username
        existing_user = await collection.find_one({"username": data.username})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username is already taken. Please choose another username.",
            )

        # Secure Argon2 password hashing
        hashed = hash_password(data.password)

        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        user_doc = {
            "id": user_id,
            "full_name": data.full_name,
            "username": data.username,
            "email": data.email,
            "mobile_number": data.mobile_number,
            "hashed_password": hashed,
            "is_active": True,
            # Optional profile fields – initialized to safe defaults so get_user_profile()
            # never raises KeyError on freshly registered accounts.
            "profile_picture": "",
            "avatar_url": "",
            "bio": "",
            "website": "",
            "is_verified": False,
            "followers_count": 0,
            "following_count": 0,
            "posts_count": 0,
            "created_at": now,
            "updated_at": now,
        }

        await collection.insert_one(user_doc)

        profile = UserProfileResponse(
            id=user_id,
            full_name=data.full_name,
            username=data.username,
            email=data.email,
            mobile_number=data.mobile_number,
            created_at=now,
        )

        access_token = create_access_token({
            "sub": user_id,
            "username": data.username,
            "email": data.email,
        })

        refresh_token = create_refresh_token({
            "sub": user_id,
            "username": data.username,
            "email": data.email,
        })

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            refresh_token=refresh_token,
            user=profile,
        )

    async def authenticate_user(self, data: LoginRequest) -> TokenResponse:
        """Authenticates user with username or email and verifies Argon2 password."""
        collection = self.col
        identifier = data.identifier.strip().lower()

        # Find user by either email or username
        user = await collection.find_one({
            "$or": [
                {"email": identifier},
                {"username": identifier},
            ]
        })

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username/email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify password using Argon2
        if not verify_password(data.password, user.get("hashed_password", "")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username/email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account has been deactivated.",
            )

        profile = UserProfileResponse(
            id=user["id"],
            full_name=user["full_name"],
            username=user["username"],
            email=user["email"],
            mobile_number=user.get("mobile_number", ""),
            created_at=user["created_at"],
            profile_picture=user.get("profile_picture") or user.get("avatar_url") or "",
            avatar_url=user.get("avatar_url") or user.get("profile_picture") or "",
            bio=user.get("bio", ""),
            website=user.get("website", ""),
            is_verified=bool(user.get("is_verified", False)),
            followers_count=int(user.get("followers_count", 0)),
            following_count=int(user.get("following_count", 0)),
            posts_count=int(user.get("posts_count", 0)),
        )

        access_token = create_access_token({
            "sub": user["id"],
            "username": user["username"],
            "email": user["email"],
        })

        refresh_token = create_refresh_token({
            "sub": user["id"],
            "username": user["username"],
            "email": user["email"],
        })

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            refresh_token=refresh_token,
            user=profile,
        )

    async def refresh_session(self, refresh_token: str) -> TokenResponse:
        """Validates a refresh token and returns a new access token and rotated refresh token."""
        try:
            payload = decode_refresh_token(refresh_token)
            user_id: Optional[str] = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token payload.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        collection = self.col
        user = await collection.find_one({"id": user_id})
        if not user or not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found or deactivated.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        profile = UserProfileResponse(
            id=user["id"],
            full_name=user["full_name"],
            username=user["username"],
            email=user["email"],
            mobile_number=user.get("mobile_number", ""),
            created_at=user["created_at"],
            profile_picture=user.get("profile_picture") or user.get("avatar_url") or "",
            avatar_url=user.get("avatar_url") or user.get("profile_picture") or "",
            bio=user.get("bio", ""),
            website=user.get("website", ""),
            is_verified=bool(user.get("is_verified", False)),
            followers_count=int(user.get("followers_count", 0)),
            following_count=int(user.get("following_count", 0)),
            posts_count=int(user.get("posts_count", 0)),
        )

        new_access_token = create_access_token({
            "sub": user["id"],
            "username": user["username"],
            "email": user["email"],
        })

        new_refresh_token = create_refresh_token({
            "sub": user["id"],
            "username": user["username"],
            "email": user["email"],
        })

        return TokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            refresh_token=new_refresh_token,
            user=profile,
        )

    async def get_user_profile(self, user_id: str) -> UserProfileResponse:
        """Retrieves user profile without password hash."""
        collection = self.col
        user = await collection.find_one({"id": user_id})

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found.",
            )

        pic = user.get("profile_picture") or user.get("avatar_url") or ""
        return UserProfileResponse(
            id=user["id"],
            full_name=user["full_name"],
            username=user["username"],
            email=user["email"],
            mobile_number=user.get("mobile_number", ""),
            created_at=user["created_at"],
            profile_picture=pic,
            avatar_url=pic,
            bio=user.get("bio", ""),
            website=user.get("website", ""),
            is_verified=bool(user.get("is_verified", False)),
            followers_count=int(user.get("followers_count", 0)),
            following_count=int(user.get("following_count", 0)),
            posts_count=int(user.get("posts_count", 0)),
        )


auth_service = AuthService()
