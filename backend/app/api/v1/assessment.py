"""API routes for the Assessment Agent.

Typical flow (what the frontend will do):
  1. POST /assessment/generate            -> quiz_id + questions WITHOUT answers (saved server-side)
  2. GET  /assessment/quizzes/{quiz_id}    -> the same student-safe quiz, e.g. to reload the page
  3. POST /assessment/quizzes/{quiz_id}/submit  -> graded against the stored answers, attempt saved
  4. GET  /assessment/students/{id}/performance -> accuracy by topic / Bloom level (Mentor Agent input)
POST /assessment/grade stays available for stateless grading (faculty tools, tests).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.agents import assessment_agent
from app.db import quiz_store
from app.schemas.assessment import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizGradeRequest,
    QuizGradeResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    QuizView,
    StudentPerformance,
)
from app.tools.llm_client import LLMError

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/ping")
async def ping():
    return {"agent": "assessment", "status": "ok"}


# Plain `def` routes: blocking LLM/Chroma/sandbox work runs in FastAPI's threadpool.
@router.post("/generate", response_model=QuizGenerateResponse)
def generate_quiz(req: QuizGenerateRequest):
    state = {
        "course_id": req.course_id,
        "quiz_topic": req.topic,
        "bloom_level": req.bloom_level,
        "num_questions": req.num_questions,
        "llm_backend": req.llm_backend,
        "question_type": req.question_type,
        "seed": req.seed,
    }
    try:
        result = assessment_agent.run(state)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    questions = result.get("generated_quiz", {}).get("questions", [])
    warnings = result.get("errors") or []
    if not questions:
        return QuizGenerateResponse(topic=req.topic, questions=[], warnings=warnings)

    quiz_id, ids = quiz_store.save_quiz(
        req.course_id, req.topic, req.question_type, req.bloom_level, questions, req.created_by
    )
    shown = [
        ({**q, "id": qid} if req.include_answers else quiz_store.public_question(q, qid))
        for q, qid in zip(questions, ids)
    ]
    return QuizGenerateResponse(quiz_id=quiz_id, topic=req.topic, questions=shown, warnings=warnings)


@router.get("/quizzes/{quiz_id}", response_model=QuizView)
def get_quiz(quiz_id: str, include_answers: bool = False):
    try:
        return quiz_store.get_quiz(quiz_id, include_answers=include_answers)
    except quiz_store.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/quizzes/{quiz_id}/submit", response_model=QuizSubmitResponse)
def submit_quiz(quiz_id: str, req: QuizSubmitRequest):
    try:
        return quiz_store.submit_attempt(
            quiz_id, req.student_id, [a.model_dump() for a in req.answers],
            llm_backend=req.llm_backend, suggest_fix=req.suggest_fix,
        )
    except quiz_store.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/students/{student_id}/performance", response_model=StudentPerformance)
def performance(student_id: str, course_id: Optional[str] = None):
    return quiz_store.student_performance(student_id, course_id)


@router.post("/grade", response_model=QuizGradeResponse)
def grade_quiz(req: QuizGradeRequest):
    state = {
        "course_id": req.course_id,
        "submissions": [s.model_dump() for s in req.submissions],
        "llm_backend": req.llm_backend,
        "suggest_fix": req.suggest_fix,
    }
    result = assessment_agent.grade(state)  # feedback failures are caught inside
    return QuizGradeResponse(**result["evaluation_result"])
