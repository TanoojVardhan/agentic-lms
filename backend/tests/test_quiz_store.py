"""Stored quizzes: answers stay server-side, submissions are graded from the
database, attempts are saved, and performance is summarized for the Mentor Agent."""
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

_vs = types.ModuleType("app.tools.vector_store")
_vs.query_course_vectorstore = lambda **kw: [{"source": "s.pdf", "text": "ctx", "chunk_index": 0}]
sys.modules.setdefault("app.tools.vector_store", _vs)

from app.config import settings  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.tools import llm_client  # noqa: E402

client = TestClient(app)

MCQ = [
    {"question": "Which layer detects local patterns?", "options": ["Conv", "Dense", "Dropout", "Flatten"],
     "correct_answer": "Conv", "bloom_level": "remember", "explanation": "Conv layers apply local filters."},
    {"question": "What does pooling give?", "options": ["Invariance", "Depth", "Bias", "Noise"],
     "correct_answer": "Invariance", "bloom_level": "understand", "explanation": "Pooling summarizes nearby outputs."},
]


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    init_db(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(settings, "code_runner_mode", "local")
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: json.dumps(MCQ))


def _generate(**extra):
    body = {"course_id": "dl", "topic": "cnn", "num_questions": 2, **extra}
    r = client.post("/api/v1/assessment/generate", json=body)
    assert r.status_code == 200
    return r.json()


def test_generate_hides_answers_and_saves():
    quiz = _generate()
    assert quiz["quiz_id"]
    for q in quiz["questions"]:
        assert q["id"] and q["correct_answer"] is None and q["explanation"] is None
    stored = client.get(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}").json()
    assert [q["id"] for q in stored["questions"]] == [q["id"] for q in quiz["questions"]]
    assert stored["questions"][0]["correct_answer"] is None
    faculty = client.get(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}?include_answers=true").json()
    assert faculty["questions"][0]["correct_answer"] == "Conv"


def test_submit_grades_from_database_and_tracks_performance(monkeypatch):
    quiz = _generate()
    q1, q2 = quiz["questions"]
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: "Pooling gives invariance to small shifts.")
    r = client.post(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}/submit", json={
        "student_id": "stu-1",
        "answers": [{"question_id": q1["id"], "student_answer": "A"},
                    {"question_id": q2["id"], "student_answer": "Depth"}],
    })
    assert r.status_code == 200
    res = r.json()
    assert (res["score"], res["total"]) == (1, 2) and res["attempt_id"]
    assert res["results"][1]["correct_answer"] == "Invariance"  # revealed only after submitting

    perf = client.get("/api/v1/assessment/students/stu-1/performance?course_id=dl").json()
    assert perf["questions_answered"] == 2 and perf["overall_accuracy"] == 50.0
    assert perf["by_topic"][0] == {"name": "cnn", "correct": 1, "total": 2, "accuracy": 50.0}
    assert perf["weak_topics"] == ["cnn"]
    assert {b["name"] for b in perf["by_bloom_level"]} == {"remember", "understand"}
    assert perf["recent_attempts"][0]["topic"] == "cnn"


def test_skipped_question_counts_wrong_and_bad_ids_rejected():
    quiz = _generate()
    q1 = quiz["questions"][0]
    res = client.post(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}/submit", json={
        "student_id": "stu-2", "answers": [{"question_id": q1["id"], "student_answer": "Conv"}],
        "suggest_fix": False}).json()
    assert (res["score"], res["total"]) == (1, 2)
    bad = client.post(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}/submit", json={
        "student_id": "stu-2", "answers": [{"question_id": "nope", "student_answer": "x"}]})
    assert bad.status_code == 400
    assert client.get("/api/v1/assessment/quizzes/missing").status_code == 404


def test_numeric_quiz_round_trip():
    quiz = _generate(question_type="numeric", seed=3)
    faculty = client.get(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}?include_answers=true").json()
    answers = [{"question_id": q["id"], "student_answer": q["correct_answer"]} for q in faculty["questions"]]
    res = client.post(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}/submit",
                      json={"student_id": "stu-3", "answers": answers}).json()
    assert res["score"] == res["total"] == 2


def test_code_quiz_hides_hidden_tests_and_reference(monkeypatch):
    code_q = json.dumps([{
        "title": "Sum", "problem": "Read two integers and print their sum.",
        "tests": [{"stdin": "1 2", "expected_output": "3"}, {"stdin": "5 5", "expected_output": "10"},
                  {"stdin": "-1 1", "expected_output": "0"}, {"stdin": "7 8", "expected_output": "15"}],
        "reference_solution": "a, b = map(int, input().split())\nprint(a + b)",
    }])
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: code_q)
    quiz = _generate(question_type="code", num_questions=1)
    q = quiz["questions"][0]
    assert q["reference_solution"] is None and len(q["tests"]) == 2  # only the visible examples

    res = client.post(f"/api/v1/assessment/quizzes/{quiz['quiz_id']}/submit", json={
        "student_id": "stu-4", "suggest_fix": False,
        "answers": [{"question_id": q["id"], "language": "python",
                     "student_answer": "a, b = map(int, input().split())\nprint(a + b)"}]}).json()
    assert res["score"] == 1 and res["results"][0]["tests_passed"] == 4
    assert res["results"][0]["correct_answer"] == ""
