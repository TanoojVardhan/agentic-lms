"""FastAPI application entrypoint — Agentic LMS backend."""
from fastapi import FastAPI

from app.api.v1 import tutor, assessment, mentor, faculty
from app.config import settings

app = FastAPI(
    title="Agentic LMS",
    description="Quad-agent collaborative AI framework for personalized education and faculty support",
    version="0.1.0",
)

app.include_router(tutor.router, prefix="/api/v1")
app.include_router(assessment.router, prefix="/api/v1")
app.include_router(mentor.router, prefix="/api/v1")
app.include_router(faculty.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.env}
