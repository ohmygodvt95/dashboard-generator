"""
Chart Widget Builder - FastAPI Application.

Main entry point for the backend API server.
Provides REST API for managing embeddable dashboard widgets
with AI-powered configuration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import connections, widgets

app = FastAPI(
    title="Chart Widget Builder API",
    description=(
        "API for creating and managing embeddable chart widgets. "
        "Uses AI to help configure charts from connected databases."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for frontend development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(connections.router)
app.include_router(widgets.router)


@app.on_event("startup")
def on_startup():
    """Initialize the database on application startup."""
    init_db()


@app.get("/api/health", tags=["health"])
def health_check():
    """Health check endpoint to verify the API is running."""
    return {"status": "ok"}
