"""API routes for the Tutor Agent."""
from fastapi import APIRouter

from app.agents import tutor_agent
from app.schemas.tutor import RetrievedChunk, TutorAskRequest, TutorAskResponse

router = APIRouter(prefix="/tutor", tags=["tutor"])


@router.get("/ping")
async def ping():
    return {"agent": "tutor", "status": "ok"}


@router.post("/ask", response_model=TutorAskResponse)
async def ask(request: TutorAskRequest) -> TutorAskResponse:
    state = {
        "student_query": request.student_query,
        "course_id": request.course_id,
        "student_id": request.student_id,
        "llm_backend": request.llm_backend,
        "mode": request.mode,
    }
    result_state = tutor_agent.run(state)

    return TutorAskResponse(
        answer=result_state.get("tutor_response", ""),
        sources=[RetrievedChunk(**c) for c in result_state.get("retrieved_chunks", [])],
        grounded=result_state.get("grounded", True),
    )
