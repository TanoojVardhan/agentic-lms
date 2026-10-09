"""API routes for the Assessment Agent."""
from fastapi import APIRouter

from app.agents import assessment_agent
from app.schemas.assessment import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizGradeRequest,
    QuizGradeResponse,
)

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/ping")
async def ping():
    return {"agent": "assessment", "status": "ok"}


@router.post("/generate", response_model=QuizGenerateResponse)
async def generate_quiz(req: QuizGenerateRequest):
    state = {
        "course_id": req.course_id,
        "quiz_topic": req.topic,
        "bloom_level": req.bloom_level,
        "num_questions": req.num_questions,
        "llm_backend": req.llm_backend,
    }
    result = assessment_agent.run(state)
    quiz = result.get("generated_quiz", {})
    return QuizGenerateResponse(topic=req.topic, questions=quiz.get("questions", []))


@router.post("/grade", response_model=QuizGradeResponse)
async def grade_quiz(req: QuizGradeRequest):
    state = {
        "course_id": req.course_id,
        "submissions": [s.model_dump() for s in req.submissions],
        "llm_backend": req.llm_backend,
    }
    result = assessment_agent.grade(state)
    return QuizGradeResponse(**result["evaluation_result"])
