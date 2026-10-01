"""Learning Path & Mentor Agent — gap detection + adaptive paths from Moodle logs. (Scaffold.)"""
from app.core.state import AgentState


def run(state: AgentState) -> AgentState:
    # TODO: fetch_moodle_user_activity(student_id, course_id)
    # TODO: detect_knowledge_gaps(performance_matrix)
    state["knowledge_gaps"] = []
    return state
