"""Offline tests for the Assessment Agent (no Ollama/Gemini/ChromaDB needed)."""
import json
import sys
import types

import pytest

# Stub heavy deps before importing the agent so tests run anywhere.
_vs = types.ModuleType("app.tools.vector_store")
_vs.query_course_vectorstore = lambda **kw: [
    {"source": "sample_syllabus.txt", "text": "A deadlock needs mutual exclusion, hold and wait, no preemption, circular wait."}
]
sys.modules.setdefault("app.tools.vector_store", _vs)

from app.agents import assessment_agent as aa  # noqa: E402

GOOD = [
    {
        "question": f"Q{i}?",
        "options": ["a", "b", "c", "d"],
        "correct_answer": "a",
        "bloom_level": "remember",
        "explanation": "Because.",
    }
    for i in range(3)
]


def _run(monkeypatch, raw, **state):
    monkeypatch.setattr(aa.llm_client, "generate", lambda *a, **k: raw)
    monkeypatch.setattr(aa, "query_course_vectorstore", _vs.query_course_vectorstore)
    base = {"course_id": "CS301-sample", "quiz_topic": "deadlocks", "num_questions": 3}
    base.update(state)
    return aa.run(base)


def test_plain_json(monkeypatch):
    out = _run(monkeypatch, json.dumps(GOOD))
    assert len(out["generated_quiz"]["questions"]) == 3


def test_fenced_json(monkeypatch):
    out = _run(monkeypatch, "```json\n" + json.dumps(GOOD) + "\n```")
    assert len(out["generated_quiz"]["questions"]) == 3


def test_noise_around_json(monkeypatch):
    out = _run(monkeypatch, "Here you go:\n" + json.dumps(GOOD) + "\nHope that helps!")
    assert len(out["generated_quiz"]["questions"]) == 3


def test_wrapped_in_object(monkeypatch):
    out = _run(monkeypatch, json.dumps({"questions": GOOD}))
    assert len(out["generated_quiz"]["questions"]) == 3


def test_bad_json_records_error(monkeypatch):
    out = _run(monkeypatch, "not json at all")
    assert out["generated_quiz"]["questions"] == []
    assert out["errors"]


def test_missing_topic(monkeypatch):
    out = _run(monkeypatch, "[]", quiz_topic=None)
    assert out["errors"]


def test_mixed_levels_cycle():
    assert aa._bloom_levels_for("mixed", 7) == aa.BLOOM_LEVELS + ["remember"]
    assert aa._bloom_levels_for("apply", 2) == ["apply", "apply"]
