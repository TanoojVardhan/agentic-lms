"""API routes for the Tutor Agent."""
from fastapi import APIRouter, HTTPException

from app.agents import tutor_agent
from app.schemas.tutor import RetrievedChunk, TutorAskRequest, TutorAskResponse
from app.tools.llm_client import LLMError

router = APIRouter(prefix="/tutor", tags=["tutor"])


@router.get("/ping")
async def ping():
    return {"agent": "tutor", "status": "ok"}


# Plain `def`, not `async def`: the agent makes blocking LLM/Chroma calls, and
# FastAPI runs sync routes in a threadpool so other requests aren't blocked.
@router.post("/ask", response_model=TutorAskResponse)
def ask(request: TutorAskRequest) -> TutorAskResponse:
    state = {
        "student_query": request.student_query,
        "course_id": request.course_id,
        "student_id": request.student_id,
        "llm_backend": request.llm_backend,
        "mode": request.mode,
    }
    try:
        result_state = tutor_agent.run(state)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return TutorAskResponse(
        answer=result_state.get("tutor_response", ""),
        sources=[RetrievedChunk(**c) for c in result_state.get("retrieved_chunks", [])],
        grounded=result_state.get("grounded", True),
    )
