"""Tutor Agent — syllabus-grounded Q&A via RAG. (Scaffold — logic not yet implemented.)"""
from app.core.state import AgentState


def run(state: AgentState) -> AgentState:
    # TODO: query_course_vectorstore(state["student_query"], state["course_id"])
    # TODO: call llm_client.generate() with retrieved context
    state["tutor_response"] = "[stub] Tutor Agent not yet implemented"
    return state
