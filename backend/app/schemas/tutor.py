"""Pydantic schemas for the Tutor Agent's API."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TutorAskRequest(BaseModel):
    student_query: str = Field(..., min_length=1)
    course_id: str
    student_id: Optional[str] = None
    llm_backend: Optional[str] = None  # ollama | openrouter | gemini — defaults to settings


class RetrievedChunk(BaseModel):
    text: str
    source: Optional[str] = None
    chunk_index: Optional[int] = None
    distance: Optional[float] = None


class TutorAskResponse(BaseModel):
    answer: str
    sources: List[RetrievedChunk] = []
