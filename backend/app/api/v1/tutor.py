"""API routes for the Tutor Agent. (Scaffold — stub responses.)"""
from fastapi import APIRouter

router = APIRouter(prefix="/tutor", tags=["tutor"])


@router.get("/ping")
async def ping():
    return {"agent": "tutor", "status": "scaffold - not yet implemented"}
