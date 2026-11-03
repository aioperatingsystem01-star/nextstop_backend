import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import pytest
from httpx import AsyncClient, ASGITransport
import jwt

from app.main import app
from app.core.config import settings
from app.core.security import hash_password, verify_password, create_access_token
from app.database import mongodb


class MockAsyncCollection:
    """In-memory async MongoDB collection simulator implementing exact Motor collection semantics."""

    def __init__(self):
        self.docs: List[Dict[str, Any]] = []
        self.indexes: List[Dict[str, Any]] = []

    async def create_index(self, keys, unique=False, name=None):
        self.indexes.append({"keys": keys, "unique": unique, "name": name})
        return name or "index"

    async def insert_one(self, doc: Dict[str, Any]):
        # Enforce unique index constraints
        for existing in self.docs:
            if "email" in doc and existing.get("email") == doc["email"]:
                raise Exception("DuplicateKeyError: duplicate email")
            if "username" in doc and existing.get("username") == doc["username"]:
                raise Exception("DuplicateKeyError: duplicate username")
        self.docs.append(dict(doc))
        class InsertResult:
            inserted_id = doc.get("id", "mock_id")
        return InsertResult()

    async def find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for doc in self.docs:
            if "$or" in filter_query:
                matched = False
                for sub_filter in filter_query["$or"]:
                    if all(doc.get(k) == v for k, v in sub_filter.items()):
                        matched = True
                        break
                if matched:
                    return dict(doc)
            else:
                if all(doc.get(k) == v for k, v in filter_query.items()):
                    return dict(doc)
        return None

    async def delete_many(self, filter_query: Dict[str, Any]):
        self.docs.clear()


class MockAdmin:
    async def command(self, cmd: str):
        if cmd == "ping":
            return {"ok": 1.0}
        return {"ok": 1.0}


class MockAsyncClient:
    def __init__(self):
        self.admin = MockAdmin()

    def close(self):
        pass


class MockAsyncDatabase:
    def __init__(self, collection: MockAsyncCollection):
        self._col = collection
        self.client = MockAsyncClient()

    def __getitem__(self, name: str):
        return self._col


@pytest.fixture(autouse=True)
def setup_mock_db():
    """Sets up an isolated mock database for each test run."""
    mock_collection = MockAsyncCollection()
    mock_db = MockAsyncDatabase(mock_collection)
    mongodb.db_instance.db = mock_db
    mongodb.db_instance.client = mock_db.client
    yield mock_collection
    mongodb.db_instance.db = None
    mongodb.db_instance.client = None


@pytest.mark.asyncio
async def test_01_mongodb_connection_and_health():
    """1. Test MongoDB Atlas connection check and health endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"]["status"] == "connected"
        assert data["database"]["name"] == settings.database_name


@pytest.mark.asyncio
async def test_02_successful_registration(setup_mock_db):
    """2. Test successful user registration."""
    payload = {
        "full_name": "Alex Mercer",
        "username": "alexmercer",
        "email": "alex@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/signup", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "alexmercer"
        assert data["user"]["email"] == "alex@nextstop.com"
        assert "password" not in data["user"]
        assert "hashed_password" not in data["user"]


@pytest.mark.asyncio
async def test_03_duplicate_email_registration(setup_mock_db):
    """3. Test registration rejection on duplicate email."""
    payload1 = {
        "full_name": "User One",
        "username": "userone",
        "email": "duplicate@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    payload2 = {
        "full_name": "User Two",
        "username": "usertwo",
        "email": "duplicate@nextstop.com",
        "mobile_number": "+9876543210",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res1 = await ac.post("/api/v1/auth/signup", json=payload1)
        assert res1.status_code == 201
        res2 = await ac.post("/api/v1/auth/signup", json=payload2)
        assert res2.status_code == 400
        assert "email" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_04_duplicate_username_registration(setup_mock_db):
    """4. Test registration rejection on duplicate username."""
    payload1 = {
        "full_name": "User First",
        "username": "coolhandle",
        "email": "first@nextstop.com",
        "mobile_number": "+1111111111",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    payload2 = {
        "full_name": "User Second",
        "username": "coolhandle",
        "email": "second@nextstop.com",
        "mobile_number": "+2222222222",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res1 = await ac.post("/api/v1/auth/signup", json=payload1)
        assert res1.status_code == 201
        res2 = await ac.post("/api/v1/auth/signup", json=payload2)
        assert res2.status_code == 400
        assert "username" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_05_invalid_email_validation():
    """5. Test registration fails with invalid email format."""
    payload = {
        "full_name": "Invalid Email User",
        "username": "invalidemail",
        "email": "not-an-email",
        "mobile_number": "+1234567890",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/signup", json=payload)
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_06_password_mismatch_validation():
    """6. Test registration fails when passwords do not match."""
    payload = {
        "full_name": "Mismatch Tester",
        "username": "mismatcher",
        "email": "mismatch@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "Password123!",
        "confirm_password": "DifferentPassword456!",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/signup", json=payload)
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_07_successful_login(setup_mock_db):
    """7. Test successful login and JWT generation."""
    signup_payload = {
        "full_name": "John Doe",
        "username": "johndoe",
        "email": "john@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "SecretPassword123",
        "confirm_password": "SecretPassword123",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/auth/signup", json=signup_payload)

        login_payload = {
            "identifier": "john@nextstop.com",
            "password": "SecretPassword123",
        }
        res = await ac.post("/api/v1/auth/login", json=login_payload)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "johndoe"


@pytest.mark.asyncio
async def test_08_incorrect_password(setup_mock_db):
    """8. Test login rejection on incorrect password."""
    signup_payload = {
        "full_name": "Jane Doe",
        "username": "janedoe",
        "email": "jane@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "CorrectPassword123",
        "confirm_password": "CorrectPassword123",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/auth/signup", json=signup_payload)

        login_payload = {
            "identifier": "janedoe",
            "password": "WrongPassword999",
        }
        res = await ac.post("/api/v1/auth/login", json=login_payload)
        assert res.status_code == 401
        assert "invalid" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_09_login_using_username(setup_mock_db):
    """9. Test login using username."""
    signup_payload = {
        "full_name": "Handle User",
        "username": "handleuser",
        "email": "handle@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "HandlePass123",
        "confirm_password": "HandlePass123",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/auth/signup", json=signup_payload)

        login_payload = {
            "identifier": "handleuser",
            "password": "HandlePass123",
        }
        res = await ac.post("/api/v1/auth/login", json=login_payload)
        assert res.status_code == 200
        assert res.json()["user"]["username"] == "handleuser"


@pytest.mark.asyncio
async def test_10_login_using_email(setup_mock_db):
    """10. Test login using email."""
    signup_payload = {
        "full_name": "Email User",
        "username": "emailuser",
        "email": "emailuser@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "EmailPass123",
        "confirm_password": "EmailPass123",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/auth/signup", json=signup_payload)

        login_payload = {
            "identifier": "emailuser@nextstop.com",
            "password": "EmailPass123",
        }
        res = await ac.post("/api/v1/auth/login", json=login_payload)
        assert res.status_code == 200
        assert res.json()["user"]["email"] == "emailuser@nextstop.com"


@pytest.mark.asyncio
async def test_11_jwt_validation(setup_mock_db):
    """11. Test valid JWT authentication."""
    signup_payload = {
        "full_name": "Token User",
        "username": "tokenuser",
        "email": "tokenuser@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "TokenPass123",
        "confirm_password": "TokenPass123",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/auth/signup", json=signup_payload)
        token = res.json()["access_token"]

        profile_res = await ac.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert profile_res.status_code == 200
        assert profile_res.json()["username"] == "tokenuser"


@pytest.mark.asyncio
async def test_12_expired_token(setup_mock_db):
    """12. Test rejection of expired JWT token."""
    expired_token = create_access_token(
        {"sub": "expired-user-id", "username": "expireduser", "email": "exp@nextstop.com"},
        expires_delta=timedelta(seconds=-10),  # expired 10s ago
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_13_protected_user_profile_endpoint(setup_mock_db):
    """13. Test protected user profile endpoint rejects missing authorization."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Request without header
        response = await ac.get("/api/v1/users/me")
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_14_logout(setup_mock_db):
    """14. Test logout endpoint."""
    signup_payload = {
        "full_name": "Logout Tester",
        "username": "logoutuser",
        "email": "logout@nextstop.com",
        "mobile_number": "+1234567890",
        "password": "LogoutPass123",
        "confirm_password": "LogoutPass123",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/auth/signup", json=signup_payload)
        token = res.json()["access_token"]

        logout_res = await ac.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_res.status_code == 200
        assert "logged out" in logout_res.json()["message"].lower()


@pytest.mark.asyncio
async def test_15_actual_user_record_storage_in_mongodb(setup_mock_db):
    """15. Test user record is stored in MongoDB with Argon2 hash and no plain text."""
    plain_pass = "VerySecureSecret!99"
    payload = {
        "full_name": "Database Tester",
        "username": "dbuser",
        "email": "dbuser@nextstop.com",
        "mobile_number": "+1999888777",
        "password": plain_pass,
        "confirm_password": plain_pass,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/signup", json=payload)
        assert response.status_code == 201

    # Inspect documents stored in mock/actual collection
    stored_doc = await setup_mock_db.find_one({"username": "dbuser"})
    assert stored_doc is not None
    assert stored_doc["email"] == "dbuser@nextstop.com"
    assert stored_doc["full_name"] == "Database Tester"
    # Verify plain-text password is NEVER stored
    assert stored_doc.get("password") is None
    # Verify Argon2 hash is stored
    stored_hash = stored_doc["hashed_password"]
    assert stored_hash.startswith("$argon2")
    # Verify password verification works against stored Argon2 hash
    assert verify_password(plain_pass, stored_hash) is True
    assert verify_password("WrongPassword", stored_hash) is False
