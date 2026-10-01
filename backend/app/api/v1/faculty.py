"""API routes for the Faculty Agent. (Scaffold — stub responses.)"""
from fastapi import APIRouter

router = APIRouter(prefix="/faculty", tags=["faculty"])


@router.get("/ping")
async def ping():
    return {"agent": "faculty", "status": "scaffold - not yet implemented"}
