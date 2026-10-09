"""API smoke tests with the vector store and LLM stubbed (no servers needed)."""
import sys
import types

from fastapi.testclient import TestClient

_vs = types.ModuleType("app.tools.vector_store")
_vs.query_course_vectorstore = lambda **kw: [
    {"source": "s.pdf", "text": "A conv layer applies filters.", "chunk_index": 0, "distance": 0.4}
]
sys.modules.setdefault("app.tools.vector_store", _vs)

from app.main import app  # noqa: E402
from app.tools import llm_client  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_numeric_generate_and_grade():
    r = client.post("/api/v1/assessment/generate", json={
        "course_id": "deep-learning", "topic": "cnn", "num_questions": 2,
        "question_type": "numeric", "seed": 5, "include_answers": True})
    assert r.status_code == 200
    qs = r.json()["questions"]
    subs = [{**q, "student_answer": q["correct_answer"]} for q in qs]
    g = client.post("/api/v1/assessment/grade", json={"course_id": "deep-learning", "submissions": subs})
    assert g.json()["score"] == 2


def test_llm_failure_is_503(monkeypatch):
    def fail(*a, **k):
        raise llm_client.LLMError("Gemini returned HTTP 429 (free-tier rate limit; wait a minute)")
    monkeypatch.setattr(llm_client, "generate", fail)
    r = client.post("/api/v1/tutor/ask", json={"student_query": "What is a conv layer?",
                                                "course_id": "deep-learning"})
    assert r.status_code == 503
    assert "rate limit" in r.json()["detail"]


def test_tutor_ok(monkeypatch):
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: "A conv layer applies filters [s.pdf #0].")
    r = client.post("/api/v1/tutor/ask", json={"student_query": "conv?", "course_id": "deep-learning"})
    assert r.status_code == 200 and r.json()["sources"]
