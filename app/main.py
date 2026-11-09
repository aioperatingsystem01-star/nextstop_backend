from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database.mongodb import connect_to_mongo, close_mongo_connection, get_database
from app.routes import auth, users, posts, chat, notifications


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    # Startup: Connect to MongoDB Atlas and verify indexes
    await connect_to_mongo()
    yield
    # Shutdown: Close database connections
    await close_mongo_connection()


app = FastAPI(
    title="Next Stop API",
    version="1.0.0",
    description=(
        "Production-ready backend API for the Next Stop social media mobile platform. "
        "Provides Argon2-hashed authentication, JWT session management, and MongoDB Atlas integration."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True if settings.cors_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers (supporting both /api/v1 and /api conventions)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(posts.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(posts.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")


@app.get(
    "/health",
    tags=["System"],
    summary="Health Check",
    description="Returns server status and database connectivity status.",
)
async def health_check():
    """Health check endpoint for Render, monitoring services, and client verification."""
    db = get_database()
    db_connected = False
    if db is not None:
        try:
            await db.client.admin.command("ping")
            db_connected = True
        except Exception:
            db_connected = False

    response_body = {
        "status": "healthy" if db_connected else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "status": "connected" if db_connected else "disconnected",
            "name": settings.database_name,
        },
        "version": "1.0.0",
    }

    # Return HTTP 503 when database is unreachable so load balancers and
    # Render health checks can detect backend degradation and retry/restart.
    if not db_connected:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response_body)

    return JSONResponse(status_code=status.HTTP_200_OK, content=response_body)


@app.get("/", tags=["System"])
async def root():
    """Root endpoint welcoming API consumers and linking to documentation."""
    return {
        "app": "Next Stop API",
        "status": "online",
        "documentation": "/docs",
        "health": "/health",
    }
