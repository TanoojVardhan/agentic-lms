"""Pydantic schemas for the Assessment Agent's quiz-generation endpoint."""
from typing import List, Optional
from pydantic import BaseModel, Field


class QuizGenerateRequest(BaseModel):
    course_id: str
    topic: str = Field(..., description="Topic/concept to quiz on, e.g. 'deadlocks'")
    bloom_level: Optional[str] = Field(
        default="mixed",
        description="One of: remember, understand, apply, analyze, evaluate, create, or 'mixed'",
    )
    num_questions: int = Field(default=5, ge=1, le=15)
    llm_backend: Optional[str] = None


class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    bloom_level: str
    explanation: str


class QuizGenerateResponse(BaseModel):
    topic: str
    questions: List[QuizQuestion]


# ---- Grading ----

class SubmittedAnswer(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    student_answer: str = Field(
        ..., description="The chosen option text, or its letter (A, B, C, D)"
    )
    bloom_level: Optional[str] = None
    explanation: Optional[str] = None  # fallback if AI feedback is unavailable


class QuizGradeRequest(BaseModel):
    course_id: str
    submissions: List[SubmittedAnswer] = Field(..., min_length=1)
    llm_backend: Optional[str] = None


class GradedQuestion(BaseModel):
    question: str
    student_answer: str
    correct_answer: str
    is_correct: bool
    bloom_level: Optional[str] = None
    feedback: str


class QuizGradeResponse(BaseModel):
    score: int
    total: int
    percentage: float
    results: List[GradedQuestion]
