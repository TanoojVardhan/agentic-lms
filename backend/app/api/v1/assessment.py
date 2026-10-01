"""API routes for the Assessment Agent. (Scaffold — stub responses.)"""
from fastapi import APIRouter

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/ping")
async def ping():
    return {"agent": "assessment", "status": "scaffold - not yet implemented"}
