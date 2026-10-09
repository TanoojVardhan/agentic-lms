"""Tests for code execution: runner (Python/C/Java), fix suggestions, code
questions and the /api/v1/code playground. They use the "local" executor, so
no Docker is needed; C and Java tests are skipped if gcc/javac are missing."""
import json
import shutil
import sys
import types

import pytest

_vs = types.ModuleType("app.tools.vector_store")
_vs.query_course_vectorstore = lambda **kw: [{"source": "s.pdf", "text": "ReLU(x)=max(0,x)", "chunk_index": 0}]
sys.modules.setdefault("app.tools.vector_store", _vs)

from app.config import settings  # noqa: E402
from app.tools import code_assistant, code_runner, llm_client  # noqa: E402
from app.agents import assessment_agent as aa  # noqa: E402
from app.agents import assessment_code as ac  # noqa: E402

needs_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
needs_java = pytest.mark.skipif(shutil.which("javac") is None, reason="javac not installed")

SUM_TESTS = [
    {"stdin": "3 4\n", "expected_output": "7"},
    {"stdin": "10 -2\n", "expected_output": "8", "hidden": True},
]
PY_SUM = "a, b = map(int, input().split())\nprint(a + b)\n"
C_SUM = '#include <stdio.h>\nint main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}\n'
JAVA_SUM = ("import java.util.*;\npublic class Main{public static void main(String[] x){"
            "Scanner s=new Scanner(System.in);System.out.println(s.nextInt()+s.nextInt());}}\n")


@pytest.fixture(autouse=True)
def local_runner(monkeypatch):
    monkeypatch.setattr(settings, "code_runner_mode", "local")
    monkeypatch.setattr(settings, "code_time_limit_s", 1.0)


# ---------------- runner ----------------

def test_python_verdicts():
    assert code_runner.execute("python", PY_SUM, SUM_TESTS)["status"] == "passed"
    assert code_runner.execute("python", "print(", SUM_TESTS)["status"] == "compile_error"
    r = code_runner.execute("python", "print(1/0)", SUM_TESTS)
    assert r["status"] == "runtime_error" and "ZeroDivisionError" in r["tests"][0]["stderr"]
    assert code_runner.execute("python", "print(99)", SUM_TESTS)["status"] == "wrong_answer"
    assert code_runner.execute("python", "while True: pass", SUM_TESTS[:1])["status"] == "timeout"


def test_no_expected_output_means_ok():
    r = code_runner.execute("python", "print(input()[::-1])", [{"stdin": "abc"}])
    assert r["status"] == "ok" and r["tests"][0]["stdout"].strip() == "cba"


def test_language_aliases_and_validation():
    assert code_runner.normalize_language("Py") == "python"
    with pytest.raises(ValueError):
        code_runner.normalize_language("rust")
    with pytest.raises(ValueError):
        code_runner.execute("python", "   ", SUM_TESTS)


def test_output_matching_is_lenient_on_spacing_and_floats():
    assert code_runner.outputs_match("1  2\n3\n", "1 2 3")
    assert code_runner.outputs_match("0.50", "0.5")
    assert code_runner.outputs_match("0.33333", "0.3333")
    assert not code_runner.outputs_match("0.34", "0.3333")
    assert not code_runner.outputs_match("1 2", "1 2 3")


def test_redact_hidden_tests():
    r = code_runner.redact_hidden(code_runner.execute("python", "print(0)", SUM_TESTS))
    visible, hidden = r["tests"]
    assert visible["stdin"] == "3 4\n"
    assert hidden["stdin"] is None and hidden["expected_output"] is None and hidden["verdict"] == "wrong_answer"


@needs_gcc
def test_c():
    assert code_runner.execute("c", C_SUM, SUM_TESTS)["status"] == "passed"
    assert code_runner.execute("c", "int main(void){ return 0 }", SUM_TESTS)["status"] == "compile_error"
    r = code_runner.execute("c", "int main(void){int *p=0;*p=1;return 0;}", SUM_TESTS[:1])
    assert r["status"] == "runtime_error" and r["tests"][0]["stderr"]


@needs_java
def test_java():
    assert code_runner.execute("java", JAVA_SUM, SUM_TESTS)["status"] == "passed"
    other = JAVA_SUM.replace("class Main", "class Solution")
    assert code_runner.execute("java", other, SUM_TESTS)["status"] == "passed"
    r = code_runner.execute("java", "public class Main{public static void main(String[] a){int[] x=new int[1];System.out.println(x[3]);}}", SUM_TESTS[:1])
    assert r["status"] == "runtime_error" and "ArrayIndexOutOfBounds" in r["tests"][0]["stderr"]
    assert "Picked up" not in r["tests"][0]["stderr"]


# ---------------- fix suggestions ----------------

def test_suggestion_parsing_variants():
    good = code_assistant._parse_suggestion('{"explanation": "Use +", "corrected_code": "print(1)"}')
    assert good["corrected_code"] == "print(1)"
    fenced = code_assistant._parse_suggestion('```json\n{"explanation": "x", "corrected_code": "a\nb"}\n```')
    assert fenced["corrected_code"] == "a\nb"  # raw newline inside a JSON string is tolerated
    prose = code_assistant._parse_suggestion("You divided by zero.\n```python\nprint(2)\n```")
    assert prose["corrected_code"] == "print(2)\n" and "divided" in prose["explanation"]


def test_suggest_fix_is_verified(monkeypatch):
    fix = json.dumps({"explanation": "Add instead of multiply.", "corrected_code": PY_SUM})
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: fix)
    bad = "a, b = map(int, input().split())\nprint(a * b)\n"
    result = code_runner.execute("python", bad, SUM_TESTS)
    s = code_assistant.suggest_fix("python", bad, result, SUM_TESTS)
    assert s["verified"] is True and "Add" in s["explanation"]


# ---------------- code questions ----------------

def _llm_question(expected_last="9"):
    return json.dumps([{
        "title": "Sum of ReLU",
        "problem": "Read n numbers on one line; print the sum of max(0, x).",
        "tests": [
            {"stdin": "1 -2 3", "expected_output": "4"},
            {"stdin": "-1 -1", "expected_output": "0"},
            {"stdin": "5 0 4", "expected_output": expected_last},
        ],
        "reference_solution": "print(sum(max(0, int(v)) for v in input().split()))",
    }])


def test_generate_code_question_validates_reference(monkeypatch):
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: _llm_question())
    out = aa.run({"course_id": "dl", "quiz_topic": "relu", "num_questions": 1, "question_type": "code"})
    q = out["generated_quiz"]["questions"][0]
    assert q["question_type"] == "code" and len(q["tests"]) == 3
    assert [t["hidden"] for t in q["tests"]] == [False, False, True]


def test_reference_output_overrides_one_wrong_llm_answer(monkeypatch):
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: _llm_question(expected_last="10"))
    q = aa.run({"course_id": "dl", "quiz_topic": "relu", "num_questions": 1,
                "question_type": "code"})["generated_quiz"]["questions"][0]
    assert q["tests"][2]["expected_output"] == "9"  # computed, not the LLM's 10


def test_broken_reference_is_discarded(monkeypatch):
    broken = _llm_question().replace("print(sum", "print(1/0+sum")
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: broken)
    out = aa.run({"course_id": "dl", "quiz_topic": "relu", "num_questions": 1, "question_type": "code"})
    assert out["generated_quiz"]["questions"] == []
    assert any("passed validation" in e for e in out["errors"])


def test_grade_code_submissions(monkeypatch):
    monkeypatch.setattr(llm_client, "generate",
                        lambda *a, **k: json.dumps({"explanation": "Use addition.", "corrected_code": PY_SUM}))
    base = {"question": "Sum two numbers", "correct_answer": "", "question_type": "code", "tests": SUM_TESTS}
    subs = [
        {**base, "language": "python", "student_answer": PY_SUM},
        {**base, "language": "python", "student_answer": "a, b = map(int, input().split())\nprint(a * b)"},
        {**base, "language": "python", "student_answer": "print("},
    ]
    res = aa.grade({"course_id": "dl", "submissions": subs})["evaluation_result"]
    assert (res["score"], res["total"]) == (1, 3)
    ok, wrong, broken = res["results"]
    assert ok["tests_passed"] == 2 and ok["suggestion"] is None
    assert wrong["suggestion"]["verified"] is True and "Expected" in wrong["feedback"]
    assert broken["feedback"].startswith("Your code did not compile")
    assert wrong["code_result"]["tests"][1]["stdin"] is None  # hidden test redacted


# ---------------- playground API ----------------

def test_code_api(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    langs = client.get("/api/v1/code/languages").json()
    assert {l["id"] for l in langs["languages"]} == {"python", "c", "java"}

    ok = client.post("/api/v1/code/run", json={"language": "python", "code": "print(input())", "stdin": "hi"})
    assert ok.json()["status"] == "ok" and ok.json()["stdout"].strip() == "hi"
    assert ok.json()["suggestion"] is None

    monkeypatch.setattr(llm_client, "generate",
                        lambda *a, **k: json.dumps({"explanation": "Close the bracket.", "corrected_code": "print(1)"}))
    bad = client.post("/api/v1/code/run", json={"language": "python", "code": "print(1"}).json()
    assert bad["status"] == "compile_error"
    assert bad["suggestion"]["corrected_code"] == "print(1)" and bad["suggestion"]["verified"] is True

    def down(*a, **k):
        raise llm_client.LLMError("Gemini returned HTTP 429")
    monkeypatch.setattr(llm_client, "generate", down)
    still = client.post("/api/v1/code/run", json={"language": "python", "code": "print(1/0)"}).json()
    assert still["status"] == "runtime_error" and "429" in still["suggestion_error"]

    assert client.post("/api/v1/code/run", json={"language": "rust", "code": "x"}).status_code == 422
