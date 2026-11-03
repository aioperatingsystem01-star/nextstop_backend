from fastapi import APIRouter, status, Depends
from app.schemas.auth import SignUpRequest, LoginRequest, TokenResponse, MessageResponse
from app.services.auth_service import auth_service
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new Next Stop user",
    description="Registers a new user with full name, username, email, mobile number, and Argon2 password hashing.",
)
async def signup(request: SignUpRequest) -> TokenResponse:
    """Creates a new user record in MongoDB Atlas and returns JWT credentials."""
    return await auth_service.register_user(request)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate existing user",
    description="Authenticates user using email or username, verifies Argon2 password hash, and returns JWT access token.",
)
async def login(request: LoginRequest) -> TokenResponse:
    """Verifies credentials and returns access token."""
    return await auth_service.authenticate_user(request)


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="User logout",
    description="Logs out user and signals client to clear local session token.",
)
async def logout(current_user: UserProfileResponse = Depends(get_current_user)) -> MessageResponse:
    """Invalidates/acknowledges client logout."""
    return MessageResponse(message=f"Successfully logged out {current_user.username}.")
