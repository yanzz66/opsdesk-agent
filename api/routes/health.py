
"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Check whether the API service is running."""

    return {
        "status": "ok",
        "service": "OpsDesk Agent API",
        "version": "1.0.0",
    }