"""
AI Dev Agency — FastAPI Application Entry Point
Handles app lifecycle, middleware, routing, and WebSocket setup.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog

from app.config import settings
from app.db.session import init_db
from app.messaging.websocket_manager import WebSocketManager
from app.workers.celery_app import celery_app  # noqa: F401 — ensure Celery is configured
from app.api.v1 import auth, projects, agents, tasks, artifacts, websocket

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter (global)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    logger.info("Starting AI Dev Agency API", version=settings.APP_VERSION)
    await init_db()
    app.state.ws_manager = WebSocketManager()
    logger.info("Database initialized, WebSocket manager ready")
    yield
    logger.info("Shutting down AI Dev Agency API")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Dev Agency",
        description="Multi-Agent AI Software Engineering Company Simulator",
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    # --- Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # --- Rate limiting ---
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # --- Routers ---
    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix, tags=["auth"])
    app.include_router(projects.router, prefix=prefix, tags=["projects"])
    app.include_router(agents.router, prefix=prefix, tags=["agents"])
    app.include_router(tasks.router, prefix=prefix, tags=["tasks"])
    app.include_router(artifacts.router, prefix=prefix, tags=["artifacts"])
    app.include_router(websocket.router, tags=["websocket"])

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.APP_VERSION}

    return app


app = create_app()
