"""API routes for the Assessment Agent."""
from fastapi import APIRouter

from app.agents import assessment_agent
from app.schemas.assessment import QuizGenerateRequest, QuizGenerateResponse

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
