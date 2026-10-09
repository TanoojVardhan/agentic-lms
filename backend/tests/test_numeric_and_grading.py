"""Offline tests: numeric questions, grading and LLM-output normalization."""
import sys
import types

_vs = types.ModuleType("app.tools.vector_store")
_vs.query_course_vectorstore = lambda **kw: [{"source": "s.pdf", "text": "ctx", "chunk_index": 0}]
sys.modules.setdefault("app.tools.vector_store", _vs)

from app.agents import assessment_agent as aa  # noqa: E402
from app.tools import numeric_questions as nq  # noqa: E402


def test_known_formula_values():
    # Keras parameter counts for well-known layers
    assert (3 * 3 * 3 + 1) * 8 == 224            # conv 8 filters, 3x3, RGB
    assert (784 + 1) * 10 == 7850                 # dense 784 -> 10
    assert 4 * 64 * (64 + 8 + 1) == 18688         # LSTM 64 units, input 8


def test_numeric_reproducible_and_topic_filtered():
    a = nq.generate_numeric("LSTM", 4, seed=3)
    assert a == nq.generate_numeric("LSTM", 4, seed=3)
    assert all("RNN" in q["question"] or "LSTM" in q["question"] for q in a)
    assert all(q["question_type"] == "numeric" and q["options"] == [] for q in a)


def test_check_numeric():
    assert nq.check_numeric(" 1,568 ", "1568")
    assert nq.check_numeric("0.79", "0.80", 0.01)
    assert not nq.check_numeric("0.75", "0.80", 0.01)
    assert not nq.check_numeric("abc", "5")


def test_run_numeric_skips_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("numeric generation must not call the LLM")
    monkeypatch.setattr(aa.llm_client, "generate", boom)
    out = aa.run({"course_id": "c", "quiz_topic": "cnn", "num_questions": 3,
                  "question_type": "numeric", "seed": 1})
    assert len(out["generated_quiz"]["questions"]) == 3


def test_normalize_accepts_level_key():
    q = {"question": "Q?", "options": ["a", "b"], "correct_answer": "a", "level": "Apply"}
    assert aa._normalize_question(q, "remember")["bloom_level"] == "apply"
    assert aa._normalize_question({"question": "Q?"}, "remember") is None


def test_no_course_material_returns_warning(monkeypatch):
    monkeypatch.setattr(aa, "query_course_vectorstore", lambda **kw: [])
    out = aa.run({"course_id": "empty", "quiz_topic": "x", "num_questions": 2})
    assert out["generated_quiz"]["questions"] == []
    assert any("no course material" in e for e in out["errors"])


def test_grade_mixed_types(monkeypatch):
    monkeypatch.setattr(aa.llm_client, "generate", lambda *a, **k: "Because the excerpt says so.")
    monkeypatch.setattr(aa, "query_course_vectorstore", _vs.query_course_vectorstore)
    subs = [
        {"question": "MCQ", "options": ["V1", "V2"], "correct_answer": "V1", "student_answer": "A"},
        {"question": "MCQ2", "options": ["x", "y"], "correct_answer": "x", "student_answer": "y"},
        {"question": "Num", "correct_answer": "224", "question_type": "numeric",
         "explanation": "formula", "student_answer": "224"},
        {"question": "Num2", "correct_answer": "7850", "question_type": "numeric",
         "explanation": "Params = (784+1) x 10 = 7850.", "student_answer": "7840"},
    ]
    res = aa.grade({"course_id": "c", "submissions": subs})["evaluation_result"]
    assert (res["score"], res["total"]) == (2, 4)
    assert res["results"][1]["feedback"] == "Because the excerpt says so."
    assert res["results"][3]["feedback"].startswith("Not quite.")
