"""Assessment Agent — Bloom's-taxonomy quiz generation + grading. (Scaffold.)"""
from app.core.state import AgentState


def run(state: AgentState) -> AgentState:
    # TODO: generate_bloom_quiz(state["quiz_topic"], state["bloom_level"])
    # TODO: evaluate_student_response(rubric, state["student_submission"])
    state["generated_quiz"] = {"stub": True}
    return state
