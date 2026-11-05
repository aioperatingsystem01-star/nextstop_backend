import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_access_token
from app.database import mongodb


class MockSearchCursor:
    """Simulates Motor AsyncIOMotorCursor for searching with sort, skip, limit, to_list."""

    def __init__(self, docs: List[Dict[str, Any]], projection: Optional[Dict[str, Any]] = None):
        self._docs = list(docs)
        self._projection = projection
        self._skip_count = 0
        self._limit_count = None
        self._sort_key = None
        self._sort_direction = 1

    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, list):
            self._sort_key = key_or_list[0][0]
            self._sort_direction = key_or_list[0][1]
        else:
            self._sort_key = key_or_list
            self._sort_direction = direction
        return self

    def skip(self, count: int):
        self._skip_count = count
        return self

    def limit(self, count: int):
        self._limit_count = count
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = list(self._docs)
        if self._sort_key:
            docs.sort(
                key=lambda d: str(d.get(self._sort_key, "")).lower(),
                reverse=(self._sort_direction == -1),
            )

        if self._skip_count:
            docs = docs[self._skip_count :]

        limit = length if length is not None else self._limit_count
        if limit is not None:
            docs = docs[:limit]

        if self._projection:
            projected = []
            for doc in docs:
                p_doc = {}
                for k, v in self._projection.items():
                    if k == "_id" and v == 0:
                        continue
                    if v == 1 and k in doc:
                        p_doc[k] = doc[k]
                projected.append(p_doc)
            return projected

        return docs


class MockSearchAsyncCollection:
    """In-memory async MongoDB collection simulator for user search tests."""

    def __init__(self):
        self.docs: List[Dict[str, Any]] = []

    async def create_index(self, keys, unique=False, name=None):
        return name or "index"

    async def insert_one(self, doc: Dict[str, Any]):
        self.docs.append(dict(doc))
        class InsertResult:
            inserted_id = doc.get("id", "mock_id")
        return InsertResult()

    def _match_condition(self, doc: Dict[str, Any], cond: Dict[str, Any]) -> bool:
        for k, v in cond.items():
            if k == "$or":
                if not any(self._match_condition(doc, sub) for sub in v):
                    return False
            elif k == "$and":
                if not all(self._match_condition(doc, sub) for sub in v):
                    return False
            elif isinstance(v, dict):
                if "$regex" in v:
                    pattern = v["$regex"]
                    flags = re.IGNORECASE if "i" in v.get("$options", "") else 0
                    val = str(doc.get(k, ""))
                    if not re.search(pattern, val, flags):
                        return False
                if "$ne" in v:
                    if doc.get(k) == v["$ne"]:
                        return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    def _filter_docs(self, filter_query: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [doc for doc in self.docs if self._match_condition(doc, filter_query)]

    async def count_documents(self, filter_query: Dict[str, Any]) -> int:
        return len(self._filter_docs(filter_query))

    def find(self, filter_query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> MockSearchCursor:
        matched = self._filter_docs(filter_query)
        return MockSearchCursor(matched, projection)

    async def find_one(self, filter_query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        matched = self._filter_docs(filter_query)
        if not matched:
            return None
        doc = dict(matched[0])
        if projection:
            p_doc = {}
            for k, v in projection.items():
                if k == "_id" and v == 0:
                    continue
                if v == 1 and k in doc:
                    p_doc[k] = doc[k]
            return p_doc
        return doc


class MockSearchDatabase:
    def __init__(self, collection: MockSearchAsyncCollection):
        self._col = collection

        class Admin:
            async def command(self, cmd: str):
                return {"ok": 1.0}

        class Client:
            admin = Admin()
            def close(self):
                pass

        self.client = Client()

    def __getitem__(self, name: str):
        return self._col


@pytest.fixture
def setup_search_db():
    mock_collection = MockSearchAsyncCollection()
    mock_db = MockSearchDatabase(mock_collection)
    mongodb.db_instance.db = mock_db
    mongodb.db_instance.client = mock_db.client

    now = datetime.now(timezone.utc)
    # Seed mock registered users
    users = [
        {
            "id": "user-harshit-01",
            "username": "harshit123",
            "full_name": "Harshit Choudhary",
            "email": "harshit@nextstop.com",
            "mobile_number": "+919876543210",
            "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$dummyhash1",
            "profile_picture": "https://images.unsplash.com/photo-1534528741775-53994a69daeb",
            "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb",
            "bio": "Content Creator & Developer",
            "is_verified": True,
            "followers_count": 120,
            "following_count": 80,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "user-rahul-02",
            "username": "rahul_dev",
            "full_name": "Rahul Sharma",
            "email": "rahul@nextstop.com",
            "mobile_number": "+919876543211",
            "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$dummyhash2",
            "profile_picture": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d",
            "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d",
            "bio": "Flutter & Mobile Enthusiast",
            "is_verified": False,
            "followers_count": 45,
            "following_count": 110,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "user-priya-03",
            "username": "priyaofficial",
            "full_name": "Priya Kapoor",
            "email": "priya@nextstop.com",
            "mobile_number": "+919876543212",
            "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$dummyhash3",
            "profile_picture": "https://images.unsplash.com/photo-1494790108377-be9c29b29330",
            "avatar_url": "https://images.unsplash.com/photo-1494790108377-be9c29b29330",
            "bio": "Visual Artist & Travel",
            "is_verified": True,
            "followers_count": 890,
            "following_count": 320,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "user-developer-04",
            "username": "developer_01",
            "full_name": "Dev Sharma",
            "email": "dev@nextstop.com",
            "mobile_number": "+919876543213",
            "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$dummyhash4",
            "profile_picture": "",
            "avatar_url": "",
            "bio": "Backend Architect",
            "is_verified": False,
            "followers_count": 12,
            "following_count": 15,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]

    mock_collection.docs = list(users)
    yield mock_collection
    mongodb.db_instance.db = None
    mongodb.db_instance.client = None


def make_auth_header(user_id: str, username: str = "testuser") -> Dict[str, str]:
    token = create_access_token({"sub": user_id, "username": username, "email": f"{username}@test.com"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_search_partial_username(setup_search_db):
    """1. Test searching by partial username 'rah' returns 'rahul_dev'."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=rah", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        usernames = [u["username"] for u in data["users"]]
        assert "rahul_dev" in usernames
        assert data["pagination"]["total"] >= 1


@pytest.mark.asyncio
async def test_search_case_insensitive(setup_search_db):
    """2. Test searching with uppercase 'HARSH' matches 'harshit123'."""
    headers = make_auth_header("user-rahul-02", "rahul_dev")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=HARSH", headers=headers)
        assert res.status_code == 200
        data = res.json()
        usernames = [u["username"] for u in data["users"]]
        assert "harshit123" in usernames


@pytest.mark.asyncio
async def test_search_by_full_name(setup_search_db):
    """3. Test searching by full name 'Priya Kapoor' or 'priya'."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=Kapoor", headers=headers)
        assert res.status_code == 200
        data = res.json()
        usernames = [u["username"] for u in data["users"]]
        assert "priyaofficial" in usernames


@pytest.mark.asyncio
async def test_search_excludes_current_user(setup_search_db):
    """4. Test that the currently authenticated user is excluded from search results."""
    # When harshit123 searches for 'harshit', harshit123 should NOT appear
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=harshit", headers=headers)
        assert res.status_code == 200
        data = res.json()
        user_ids = [u["id"] for u in data["users"]]
        assert "user-harshit-01" not in user_ids


@pytest.mark.asyncio
async def test_search_pagination(setup_search_db):
    """5. Test pagination limit and page offsets."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Search 'a' matches rahul, priya, developer
        res = await ac.get("/api/v1/users/search?q=a&page=1&limit=2", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["users"]) <= 2
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["limit"] == 2
        assert data["pagination"]["has_more"] is True


@pytest.mark.asyncio
async def test_search_never_returns_private_data(setup_search_db):
    """6. Test security rules: passwords, password hashes, emails, phone numbers are never returned."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=rahul", headers=headers)
        assert res.status_code == 200
        data = res.json()
        for user in data["users"]:
            assert "password" not in user
            assert "hashed_password" not in user
            assert "email" not in user
            assert "mobile_number" not in user
            # Public fields must be present
            assert "id" in user
            assert "username" in user
            assert "full_name" in user
            assert "bio" in user
            assert "followers_count" in user
            assert "following_count" in user
            assert "is_verified" in user


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty_list(setup_search_db):
    """7. Test empty query returns empty list without database query."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["users"] == []
        assert data["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_search_strips_leading_at_symbol(setup_search_db):
    """8. Test query with leading '@' symbol like '@rahul_dev' matches 'rahul_dev'."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=@rahul", headers=headers)
        assert res.status_code == 200
        data = res.json()
        usernames = [u["username"] for u in data["users"]]
        assert "rahul_dev" in usernames


@pytest.mark.asyncio
async def test_search_without_auth_rejected(setup_search_db):
    """9. Test unauthenticated request is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/search?q=rahul")
        assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_user_profile_by_id(setup_search_db):
    """10. Test fetching public profile of another user by ID."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/user-rahul-02", headers=headers)
        assert res.status_code == 200
        user = res.json()
        assert user["id"] == "user-rahul-02"
        assert user["username"] == "rahul_dev"
        assert user["full_name"] == "Rahul Sharma"
        assert "email" not in user
        assert "password" not in user


@pytest.mark.asyncio
async def test_get_user_profile_by_id_not_found(setup_search_db):
    """11. Test 404 returned for nonexistent user ID."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/users/nonexistent-id", headers=headers)
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_search_alternate_route_prefix(setup_search_db):
    """12. Test search via /api/users/search (without /v1) also works."""
    headers = make_auth_header("user-harshit-01", "harshit123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/users/search?q=priya", headers=headers)
        assert res.status_code == 200
        data = res.json()
        usernames = [u["username"] for u in data["users"]]
        assert "priyaofficial" in usernames
