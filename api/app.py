
"""OpsDesk Agent FastAPI application."""

from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from fastapi import FastAPI

from api.routes.health import router as health_router
from api.routes.knowledge import router as knowledge_router
from api.routes.tickets import router as tickets_router


app = FastAPI(
    title="OpsDesk Agent API",
    description="Enterprise IT AI Agent Backend",
    version="1.0.0",
)

app.include_router(health_router)
app.include_router(knowledge_router)
app.include_router(tickets_router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to OpsDesk Agent API",
        "docs": "/docs",
        "health": "/health",
    }