"""Faculty Copilot Agent — lecture drafting, question banks, cohort analytics. (Scaffold.)"""
from app.core.state import AgentState


def run(state: AgentState) -> AgentState:
    # TODO: draft_lecture_notes(topic, key_concepts)
    # TODO: generate_cohort_analytics(course_id)
    state["drafted_material"] = "[stub] Faculty Copilot not yet implemented"
    return state
