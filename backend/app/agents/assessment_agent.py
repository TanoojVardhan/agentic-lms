"""Assessment Agent — Bloom's-taxonomy quiz generation (grading comes later).

Mirrors the Tutor Agent's pattern: retrieve grounded context from the course's
ChromaDB collection, then ask the LLM to produce quiz questions strictly from
that context, spread across Bloom's Taxonomy levels, as structured JSON.
"""
from __future__ import annotations

import json
import re

from app.core.state import AgentState
from app.tools import llm_client
from app.tools.vector_store import query_course_vectorstore

BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

SYSTEM_PROMPT = (
    "You are an expert assessment designer. You write multiple-choice quiz "
    "questions strictly grounded in the COURSE MATERIAL provided below — "
    "never invent facts outside it. Each question must be tagged with the "
    "Bloom's Taxonomy level it targets (remember, understand, apply, "
    "analyze, evaluate, create). "
    "Respond with ONLY valid JSON — no markdown code fences, no commentary, "
    "no text before or after the JSON. The JSON must be a list of objects, "
    'each shaped exactly like: {"question": str, "options": [str, str, str, str], '
    '"correct_answer": str (must exactly match one of the options), '
    '"bloom_level": str, "explanation": str}.'
)


def _bloom_levels_for(bloom_level: str | None, num_questions: int) -> list[str]:
    """Decide which Bloom's level each question should target."""
    if bloom_level and bloom_level.lower() != "mixed":
        level = bloom_level.lower()
        return [level] * num_questions
    # "mixed": cycle through the taxonomy so a run of N questions spans levels
    return [BLOOM_LEVELS[i % len(BLOOM_LEVELS)] for i in range(num_questions)]


def _extract_json(raw: str):
    """LLMs sometimes wrap JSON in ```json fences or add stray text. Strip that."""
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    # Fall back to grabbing the outermost [...] if there's still leading/trailing noise
    if not text.startswith("["):
        bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket_match:
            text = bracket_match.group(0)
    return json.loads(text)


def run(state: AgentState) -> AgentState:
    course_id = state.get("course_id")
    topic = state.get("quiz_topic")
    bloom_level = state.get("bloom_level") or "mixed"
    num_questions = state.get("num_questions", 5)

    errors = state.get("errors") or []

    if not topic or not course_id:
        errors.append("assessment_agent: missing quiz_topic or course_id")
        state["errors"] = errors
        state["generated_quiz"] = {"questions": []}
        return state

    chunks = query_course_vectorstore(query=topic, course_id=course_id, k=6)
    context = "\n\n".join(f"[{c['source']}] {c['text']}" for c in chunks)

    levels_wanted = _bloom_levels_for(bloom_level, num_questions)
    level_instructions = ", ".join(levels_wanted)

    prompt = (
        f"COURSE MATERIAL:\n{context if context else '(no material found — say so)'}\n\n"
        f"TASK: Write exactly {num_questions} multiple-choice quiz questions about "
        f"'{topic}', using ONLY the course material above.\n"
        f"Target these Bloom's Taxonomy levels, in this order, one per question: "
        f"{level_instructions}.\n"
        f"Each question needs exactly 4 options, one correct answer (verbatim match "
        f"to one option), and a one-sentence explanation of why it's correct.\n"
        f"Output ONLY the JSON list, nothing else."
    )

    raw = llm_client.generate(
        prompt,
        backend=state.get("llm_backend"),
        system=SYSTEM_PROMPT,
    )

    try:
        questions = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        errors.append(f"assessment_agent: failed to parse LLM JSON output ({e})")
        state["errors"] = errors
        state["generated_quiz"] = {"questions": [], "raw_output": raw}
        return state

    state["generated_quiz"] = {"questions": questions}
    state["retrieved_chunks"] = chunks
    return state
