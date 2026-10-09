"""Tutor Agent — syllabus-grounded Q&A via RAG.

Retrieves relevant chunks from the course's ChromaDB collection, then asks
the configured LLM backend to answer using only that retrieved context
(grounding), rather than its own general knowledge — this is what keeps
answers syllabus-grounded instead of hallucinated.

Two modes, selected per-request via state["mode"]:
  - "strict" (default): if the course material doesn't cover the question,
    say so plainly rather than guessing. Zero hallucination risk — the
    agent only ever speaks from ingested course content.
  - "hybrid": if the course material doesn't cover the question, fall back
    to the LLM's own general knowledge instead of refusing — but the
    answer is clearly labeled as general knowledge, not verified against
    the course, so it's never confused with a grounded, cited answer.
"""
from app.config import settings
from app.core.state import AgentState
from app.tools import llm_client
from app.tools.vector_store import query_course_vectorstore

SYSTEM_PROMPT = (
    "You are a course tutor. Answer the student's question using ONLY the "
    "provided course material excerpts below. If the excerpts don't contain "
    "enough information to answer, say so plainly instead of guessing or "
    "using outside knowledge. Keep answers concise and cite which excerpt "
    "(by its source/chunk number) you drew on."
)

HYBRID_FALLBACK_SYSTEM_PROMPT = (
    "You are a helpful tutor. The student's course material does not cover "
    "this question. Answer from your own general knowledge as accurately "
    "and concisely as you can. Your answer will be shown to the student "
    "clearly labeled as general knowledge, not verified against their "
    "course material, so just give the best accurate answer you can."
)

HYBRID_LABEL = (
    "⚠️ General knowledge (not from your course material — not "
    "verified against it):\n\n"
)

NO_MATERIAL_MESSAGE = (
    "I don't have any course material indexed for this course yet, so I "
    "can't answer that in a grounded way."
)

STRICT_UNGROUNDED_MESSAGE = (
    "I don't have enough information in your course material to answer "
    "that. Try rephrasing, or ask your instructor if this topic is "
    "actually covered in the course."
)


def _is_grounded(chunks, threshold: float) -> bool:
    """Decide whether the top retrieved chunk is actually relevant.

    Chroma always returns its k-nearest chunks even when none of them are
    truly relevant, so an empty list and a low-relevance list both need to
    be treated as "not grounded" — we use the best (smallest) distance as
    an approximate relevance signal.
    """
    if not chunks:
        return False
    best_distance = chunks[0].get("distance")
    if best_distance is None:
        # Some backends don't return distance — assume grounded rather than
        # silently discarding a non-empty retrieval result.
        return True
    return best_distance <= threshold


def run(state: AgentState) -> AgentState:
    query = state.get("student_query")
    course_id = state.get("course_id")
    mode = (state.get("mode") or "strict").lower()
    if mode not in ("strict", "hybrid"):
        mode = "strict"

    if not query or not course_id:
        state["tutor_response"] = "Missing student_query or course_id."
        state["retrieved_chunks"] = []
        state["grounded"] = False
        return state

    chunks = query_course_vectorstore(query=query, course_id=course_id)
    state["retrieved_chunks"] = chunks

    grounded = _is_grounded(chunks, settings.rag_hybrid_distance_threshold)
    state["grounded"] = grounded

    if grounded:
        context = "\n\n".join(
            f"[{c['source']} #{c['chunk_index']}]\n{c['text']}" for c in chunks
        )
        prompt = f"Course material excerpts:\n\n{context}\n\nStudent question: {query}"
        state["tutor_response"] = llm_client.generate(
            prompt=prompt,
            backend=state.get("llm_backend"),
            system=SYSTEM_PROMPT,
        )
        return state

    # Not grounded — behavior now depends on mode.
    if mode == "strict":
        state["tutor_response"] = (
            NO_MATERIAL_MESSAGE if not chunks else STRICT_UNGROUNDED_MESSAGE
        )
        return state

    # hybrid: fall back to the LLM's own general knowledge, clearly labeled.
    fallback_answer = llm_client.generate(
        prompt=query,
        backend=state.get("llm_backend"),
        system=HYBRID_FALLBACK_SYSTEM_PROMPT,
    )
    state["tutor_response"] = HYBRID_LABEL + fallback_answer
    return state
