# Ludo Game Backend - Main Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging

# Import game modules
from app.game_engine import GameEngine
from app.room_manager import RoomManager
from app.websocket_handler import setup_websocket_handlers
from app.api_routes import router as api_router
from app.routes.auth_api import router as auth_router
from app.routes.payments import router as payments_router
from app.routes.tournaments import router as tournaments_router
from app.routes.messages_api import router as messages_router
from app.db_connection import init_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize managers (singleton)
room_manager = RoomManager()
game_engine = GameEngine()
# expose managers on app state for route handlers to use

# Global lifespan context
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage app lifecycle
    """
    logger.info("Starting Ludo Game Server...")
    try:
        await init_db()
    except Exception as exc:
        # Do not crash the whole app for local development if DB is not configured.
        logger.warning(
            "Database initialization failed, continuing in local/in-memory mode: %s",
            exc,
        )
    yield
    try:
        await close_db()
    except Exception:
        logger.warning("Error closing DB connection during shutdown")
    logger.info("Ludo Game Server stopped")

app = FastAPI(
    title="Ludo Game Server",
    description="Multiplayer Ludo Game API with WebSocket Support",
    version="1.0.0",
    lifespan=lifespan,
)

# attach singletons to app state so routers can access them
app.state.room_manager = room_manager
app.state.game_engine = game_engine

# Add CORS middleware - accept any origin so the mobile app works
# from any network (Kathmandu, Pokhara, etc.) without configuration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when allow_origins is "*"
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Include API routes
app.include_router(api_router, prefix="/api", tags=["api"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(payments_router, prefix="/api", tags=["payments"])
app.include_router(tournaments_router, prefix="/api", tags=["tournaments"])
app.include_router(messages_router, prefix="/api", tags=["messages"])

# Setup WebSocket handlers
setup_websocket_handlers(app, room_manager, game_engine)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "message": "Ludo Game Server is running",
        "version": "1.0.0",
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Ludo Game Server",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "api": "/api",
            "docs": "/docs",
            "websocket": "/ws",
        },
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
