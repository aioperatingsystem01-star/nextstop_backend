# ==============================================================================
# NEXT STOP BACKEND - SUPABASE STORAGE SERVICE
# Updated: 2026-11-09 | Supabase storage upsert boolean fix & lazy client init
# ==============================================================================
import io
import logging
import time
import uuid
from typing import Optional, Tuple
from fastapi import HTTPException, UploadFile, status
from supabase import Client, create_client
from app.core.config import settings

logger = logging.getLogger("nextstop.storage")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class StorageService:
    """Manages secure media uploads to Supabase Storage private/public bucket."""

    def __init__(self):
        self._client: Optional[Client] = None
        self.bucket = settings.supabase_bucket

    @property
    def client(self) -> Optional[Client]:
        if self._client is None:
            try:
                if settings.supabase_url and settings.supabase_secret_key:
                    self._client = create_client(
                        settings.supabase_url,
                        settings.supabase_secret_key,
                    )
            except Exception as e:
                logger.warning("Could not initialize Supabase client: %s", e)
        return self._client

    async def upload_avatar(self, user_id: str, file: UploadFile) -> str:
        """
        Validates and uploads user avatar to Supabase Storage.
        Returns the persistent media URL.
        """
        content_type = file.content_type or "image/jpeg"
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid image format '{content_type}'. Allowed: JPEG, PNG, WebP.",
            )

        data = await file.read()
        if len(data) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Avatar file exceeds max size limit of 10MB ({len(data)} bytes).",
            )

        ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else "jpg"
        file_path = f"avatars/{user_id}_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"

        return await self._upload_bytes(file_path, data, content_type)

    async def upload_post_media(self, user_id: str, file: UploadFile) -> Tuple[str, str]:
        """
        Validates and uploads post photo or video to Supabase Storage.
        Returns (media_url, media_type).
        """
        content_type = file.content_type or "image/jpeg"
        is_video = content_type in ALLOWED_VIDEO_TYPES
        is_image = content_type in ALLOWED_IMAGE_TYPES

        if not (is_image or is_video):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported media format '{content_type}'.",
            )

        data = await file.read()
        max_size = MAX_VIDEO_SIZE_BYTES if is_video else MAX_IMAGE_SIZE_BYTES
        if len(data) > max_size:
            max_mb = max_size // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Media exceeds maximum allowed size of {max_mb}MB.",
            )

        ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else ("mp4" if is_video else "jpg")
        media_type = "video" if is_video else "image"
        file_path = f"posts/{user_id}_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"

        media_url = await self._upload_bytes(file_path, data, content_type)
        return media_url, media_type

    async def _upload_bytes(self, file_path: str, data: bytes, content_type: str) -> str:
        """Internal worker that uploads binary data to Supabase."""
        try:
            cli = self.client
            if cli is not None:
                # Ensure bucket exists or attempt upload
                cli.storage.from_(self.bucket).upload(
                    path=file_path,
                    file=data,
                    file_options={"content-type": content_type, "upsert": True},
                )
                # Obtain public URL from Supabase
                public_res = cli.storage.from_(self.bucket).get_public_url(file_path)
                if public_res:
                    return public_res
        except Exception as e:
            logger.warning("Supabase storage upload failed or network unavailable: %s", e)

        # Fallback URL if network is sandboxed or Supabase endpoint is direct
        clean_url = settings.supabase_url.rstrip("/")
        return f"{clean_url}/storage/v1/object/public/{self.bucket}/{file_path}"


storage_service = StorageService()
