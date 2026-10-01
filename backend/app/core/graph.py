"""LangGraph state-graph wiring the four agents together.

Scaffold only: each agent is wired as a node, but the routing is currently
linear/manual. Real conditional routing (e.g. Mentor Agent's gaps feeding
into Tutor Agent's next response) gets added once each agent's own logic is
implemented.
"""
from langgraph.graph import StateGraph, END

from app.core.state import AgentState
from app.agents import tutor_agent, assessment_agent, mentor_agent, faculty_agent


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("tutor", tutor_agent.run)
    graph.add_node("assessment", assessment_agent.run)
    graph.add_node("mentor", mentor_agent.run)
    graph.add_node("faculty", faculty_agent.run)

    # TODO: replace with real conditional edges once agent logic exists.
    graph.set_entry_point("tutor")
    graph.add_edge("tutor", END)

    return graph.compile()


agentic_graph = build_graph()
