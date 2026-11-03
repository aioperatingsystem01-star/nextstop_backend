import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class SignUpRequest(BaseModel):
    """Schema for new user registration."""
    full_name: str = Field(..., min_length=2, max_length=100, description="Full Name of the user")
    username: str = Field(..., min_length=3, max_length=30, description="Unique username handle")
    email: EmailStr = Field(..., description="Valid unique email address")
    mobile_number: str = Field(..., min_length=7, max_length=20, description="Contact mobile number")
    password: str = Field(..., min_length=6, description="Account password (min 6 characters)")
    confirm_password: str = Field(..., min_length=6, description="Confirmation of account password")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("Full Name must have at least 2 characters")
        return clean

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[a-z0-9_.]+$", clean):
            raise ValueError("Username can only contain alphanumeric characters, underscores, and dots")
        if len(clean) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return clean

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: EmailStr) -> str:
        return str(v).strip().lower()

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = v.strip()
        # Accept optional '+' followed by digits, spaces, dashes
        if not re.match(r"^\+?[0-9\s\-]{7,20}$", clean):
            raise ValueError("Invalid mobile number format")
        return clean

    @model_validator(mode="after")
    def verify_passwords_match(self) -> "SignUpRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password and confirmation password do not match")
        return self


class LoginRequest(BaseModel):
    """Schema for user authentication."""
    identifier: str = Field(..., min_length=1, description="Registered email or username")
    password: str = Field(..., min_length=1, description="Account password")

    @field_validator("identifier")
    @classmethod
    def clean_identifier(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Identifier (email or username) is required")
        return clean


class UserProfileResponse(BaseModel):
    """Public user profile information. Never includes password hashes."""
    id: str = Field(..., description="Unique user identifier")
    full_name: str = Field(..., description="User's full name")
    username: str = Field(..., description="User's unique handle")
    email: str = Field(..., description="User's email address")
    mobile_number: str = Field(..., description="User's mobile number")
    created_at: datetime = Field(..., description="Account creation timestamp")


class TokenResponse(BaseModel):
    """Access token and user profile returned on successful login and signup."""
    access_token: str = Field(..., description="JWT bearer access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token validity duration in seconds")
    user: UserProfileResponse = Field(..., description="Authenticated user profile")


class MessageResponse(BaseModel):
    """Generic status/message response."""
    message: str = Field(..., description="Response status message")
