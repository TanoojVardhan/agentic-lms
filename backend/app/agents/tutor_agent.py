"""Tutor Agent — syllabus-grounded Q&A via RAG.

Retrieves relevant chunks from the course's ChromaDB collection, then asks
the configured LLM backend to answer using only that retrieved context
(grounding), rather than its own general knowledge — this is what keeps
answers syllabus-grounded instead of hallucinated.
"""
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


def run(state: AgentState) -> AgentState:
    query = state.get("student_query")
    course_id = state.get("course_id")

    if not query or not course_id:
        state["tutor_response"] = "Missing student_query or course_id."
        state["retrieved_chunks"] = []
        return state

    chunks = query_course_vectorstore(query=query, course_id=course_id)
    state["retrieved_chunks"] = chunks

    if not chunks:
        state["tutor_response"] = (
            "I don't have any course material indexed for this course yet, "
            "so I can't answer that in a grounded way."
        )
        return state

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
