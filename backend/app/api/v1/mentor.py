"""API routes for the Mentor Agent. (Scaffold — stub responses.)"""
from fastapi import APIRouter

router = APIRouter(prefix="/mentor", tags=["mentor"])


@router.get("/ping")
async def ping():
    return {"agent": "mentor", "status": "scaffold - not yet implemented"}
