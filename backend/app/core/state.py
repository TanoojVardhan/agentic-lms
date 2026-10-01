"""Shared LangGraph state passed between all four agents.

This is the backbone of the project's novelty claim: agents don't just run
independently, they read/write a common state object so one agent's output
(e.g. Mentor Agent's detected gaps) becomes another's input (e.g. Tutor
Agent's scaffolding context).
"""
from typing import TypedDict, Optional, List, Dict, Any


class AgentState(TypedDict, total=False):
    # Identity / routing
    student_id: Optional[str]
    course_id: Optional[str]

    # Tutor Agent
    student_query: Optional[str]
    retrieved_chunks: Optional[List[Dict[str, Any]]]
    tutor_response: Optional[str]

    # Assessment Agent
    quiz_topic: Optional[str]
    bloom_level: Optional[str]
    generated_quiz: Optional[Dict[str, Any]]
    student_submission: Optional[str]
    evaluation_result: Optional[Dict[str, Any]]

    # Learning Path & Mentor Agent
    interaction_logs: Optional[Dict[str, Any]]
    knowledge_gaps: Optional[List[str]]
    learning_path: Optional[Dict[str, Any]]

    # Faculty Copilot Agent
    faculty_prompt: Optional[str]
    drafted_material: Optional[str]
    cohort_analytics: Optional[Dict[str, Any]]

    # Bookkeeping
    llm_backend: Optional[str]   # ollama | openrouter | gemini — set per-request
    errors: Optional[List[str]]
