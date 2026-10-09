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


def _normalize_question(q, default_level: str):
    """LLMs often drift from the requested JSON keys (e.g. "level" instead of
    "bloom_level"). Accept common variants and fall back to the level we asked
    for; return None if the item is too broken to use."""
    if not isinstance(q, dict):
        return None
    question = q.get("question")
    options = q.get("options")
    correct = q.get("correct_answer") or q.get("answer") or q.get("correct")
    if not question or not isinstance(options, list) or not options or not correct:
        return None
    level = (
        q.get("bloom_level") or q.get("level") or q.get("bloom")
        or q.get("bloomLevel") or default_level
    )
    level = str(level).strip().lower()
    if level not in BLOOM_LEVELS:
        level = default_level
    return {
        "question": str(question),
        "options": [str(o) for o in options],
        "correct_answer": str(correct),
        "bloom_level": level,
        "explanation": str(q.get("explanation") or ""),
    }


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

    # Some models wrap the list: {"questions": [...]}
    if isinstance(questions, dict):
        questions = questions.get("questions", [])
    if not isinstance(questions, list):
        questions = []

    cleaned = []
    for i, q in enumerate(questions):
        default_level = levels_wanted[i] if i < len(levels_wanted) else levels_wanted[-1]
        item = _normalize_question(q, default_level)
        if item:
            cleaned.append(item)
    if len(cleaned) < num_questions:
        errors.append(
            f"assessment_agent: requested {num_questions} questions, got {len(cleaned)} usable"
        )
        state["errors"] = errors

    state["generated_quiz"] = {"questions": cleaned}
    state["retrieved_chunks"] = chunks
    return state


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

FEEDBACK_SYSTEM_PROMPT = (
    "You are a supportive course tutor giving feedback on a wrong quiz answer. "
    "Using ONLY the course material excerpts provided, explain in 2-3 short "
    "sentences why the student's answer is incorrect and why the correct "
    "answer is right. Do not invent facts outside the excerpts."
)


def _resolve_answer(student_answer: str, options: list[str]) -> str:
    """Accept either the option text or a letter (A/B/C/D) and return the text."""
    ans = (student_answer or "").strip()
    if len(ans) == 1 and ans.upper() in "ABCDEF":
        idx = ord(ans.upper()) - ord("A")
        if idx < len(options):
            return options[idx]
    return ans


def _norm(s: str) -> str:
    return " ".join((s or "").split()).casefold()


def grade(state: AgentState) -> AgentState:
    """Grade a list of submitted quiz answers.

    Correct answers are marked with no LLM call. For wrong answers, retrieve
    course material for the question and ask the LLM for short grounded
    feedback; if that fails, fall back to the question's stored explanation.
    """
    course_id = state.get("course_id")
    submissions = state.get("submissions") or []
    errors = state.get("errors") or []

    results = []
    score = 0
    for sub in submissions:
        options = sub.get("options") or []
        chosen = _resolve_answer(sub.get("student_answer", ""), options)
        correct = sub.get("correct_answer", "")
        is_correct = _norm(chosen) == _norm(correct)

        if is_correct:
            score += 1
            feedback = "Correct."
        else:
            feedback = sub.get("explanation") or f"The correct answer is: {correct}"
            try:
                chunks = query_course_vectorstore(
                    query=sub.get("question", ""), course_id=course_id, k=3
                )
                if chunks:
                    context = "\n\n".join(f"[{c['source']}] {c['text']}" for c in chunks)
                    prompt = (
                        f"Course material excerpts:\n\n{context}\n\n"
                        f"Question: {sub.get('question')}\n"
                        f"Student's answer: {chosen}\n"
                        f"Correct answer: {correct}\n\n"
                        f"Explain the mistake briefly."
                    )
                    feedback = llm_client.generate(
                        prompt,
                        backend=state.get("llm_backend"),
                        system=FEEDBACK_SYSTEM_PROMPT,
                    ).strip()
            except Exception as e:  # never let feedback failure block the score
                errors.append(f"assessment_agent.grade: feedback unavailable ({e})")

        results.append(
            {
                "question": sub.get("question", ""),
                "student_answer": chosen,
                "correct_answer": correct,
                "is_correct": is_correct,
                "bloom_level": sub.get("bloom_level"),
                "feedback": feedback,
            }
        )

    total = len(results)
    state["evaluation_result"] = {
        "score": score,
        "total": total,
        "percentage": round(100 * score / total, 1) if total else 0.0,
        "results": results,
    }
    if errors:
        state["errors"] = errors
    return state
