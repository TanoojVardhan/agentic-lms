"""Code questions for the Assessment Agent (question_type="code").

Generation: the LLM writes a programming exercise in the standard judge
format (read stdin, print stdout), five test cases and a Python reference
solution. Before a question is served, the reference solution is run on the
tests. A question is kept only if the reference runs cleanly and agrees with
at least half of the LLM's own expected outputs; the expected outputs are then
taken from the reference run, because computed answers are more reliable
than ones the model wrote by hand.

Grading: the student's code (Python, C or Java) runs against all tests in the
sandbox; failures come back with errors and an LLM-suggested fix that has
itself been run against the tests.
"""
from __future__ import annotations

import json
import re

from app.tools import llm_client
from app.tools.code_assistant import suggest_fix
from app.tools.code_runner import RunnerError, execute, outputs_match, redact_hidden

VISIBLE_TESTS = 2  # the first tests are shown to students as examples; the rest are hidden

CODE_GEN_SYSTEM_PROMPT = (
    "You write short programming exercises for a university course. Every "
    "exercise must be solvable in Python, C or Java using only the standard "
    "library. Respond with ONLY valid JSON, no markdown fences: a list of "
    'objects shaped exactly like {"title": str, "problem": str, '
    '"tests": [{"stdin": str, "expected_output": str}], "reference_solution": str}.'
)


def _parse_list(raw: str) -> list:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1], strict=False)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _validate(item: dict) -> dict | None:
    """Run the reference solution; return a finished question or None."""
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    problem = str(item.get("problem") or "").strip()
    reference = item.get("reference_solution")
    raw_tests = item.get("tests")
    if not problem or not reference or not isinstance(raw_tests, list) or len(raw_tests) < 3:
        return None
    tests = [
        {"stdin": str(t.get("stdin") or ""), "expected_output": str(t.get("expected_output") or "")}
        for t in raw_tests[:8] if isinstance(t, dict)
    ]
    run = execute("python", str(reference), [{"stdin": t["stdin"]} for t in tests])
    if run["status"] != "ok":  # reference crashed, timed out or did not compile
        return None
    agree = sum(outputs_match(r["stdout"], t["expected_output"]) for r, t in zip(run["tests"], tests))
    if agree < len(tests) / 2:  # reference and stated answers disagree: untrustworthy
        return None
    final_tests = [
        {"stdin": t["stdin"], "expected_output": r["stdout"].strip(), "hidden": i >= VISIBLE_TESTS}
        for i, (t, r) in enumerate(zip(tests, run["tests"]))
    ]
    return {
        "question": f"{title}\n\n{problem}" if title else problem,
        "options": [],
        "correct_answer": "",
        "bloom_level": "apply",
        "explanation": "Your program must produce the expected output for every test case.",
        "question_type": "code",
        "tests": final_tests,
        "reference_solution": str(reference),
        "languages": ["python", "c", "java"],
    }


def generate_code_questions(topic: str, num_questions: int, context: str,
                            backend: str | None) -> tuple[list[dict], list[str]]:
    """Returns (validated questions, error messages). Raises LLMError if the LLM is down."""
    errors: list[str] = []
    questions: list[dict] = []
    for _attempt in range(2):  # one retry for questions that failed validation
        missing = num_questions - len(questions)
        if missing <= 0:
            break
        prompt = (
            f"COURSE MATERIAL (for context):\n{context or '(none)'}\n\n"
            f"TASK: Write exactly {missing} short programming exercises related to '{topic}'.\n"
            "Rules:\n"
            "- The program reads all input from standard input and prints the answer to standard output.\n"
            "- 'problem' states the task, the exact input format and the exact output format, "
            "and includes one worked example.\n"
            "- Use only the standard library (no NumPy). Print real numbers rounded to 4 decimal places.\n"
            "- Do not name a programming language in 'problem': students may answer in Python, C or Java.\n"
            "- Write formulas in plain text, e.g. 1 / (1 + e^(-x)); no LaTeX, no $ signs.\n"
            "- Give 5 tests: typical cases and edge cases, with small inputs.\n"
            "- 'reference_solution' is a complete Python 3 program that solves the exercise.\n"
            "Output ONLY the JSON list."
        )
        raw = llm_client.generate(prompt, backend=backend, system=CODE_GEN_SYSTEM_PROMPT)
        for item in _parse_list(raw):
            try:
                question = _validate(item)
            except RunnerError as exc:
                errors.append(f"assessment_agent: could not validate code questions ({exc})")
                return questions, errors
            except ValueError:
                question = None
            if question:
                questions.append(question)
            if len(questions) >= num_questions:
                break
    if len(questions) < num_questions:
        errors.append(
            f"assessment_agent: requested {num_questions} code questions, "
            f"{len(questions)} passed validation"
        )
    return questions, errors


def _feedback(result: dict) -> str:
    if result["status"] == "passed":
        return f"All {result['total']} tests passed."
    if result["status"] == "compile_error":
        lines = (result.get("compile_output") or "").strip().splitlines()
        return "Your code did not compile:\n" + "\n".join(lines[:8])
    msg = f"Passed {result['passed']} of {result['total']} tests."
    first = next((t for t in result["tests"] if t["verdict"] != "passed"), None)
    if first is None:
        return msg
    label = first["verdict"].replace("_", " ")
    if first["hidden"]:
        return f"{msg} A hidden test failed ({label})."
    detail = f"{msg} First failing test ({label}), input:\n{first['stdin'].strip()}"
    if first["verdict"] == "wrong_answer":
        detail += f"\nExpected:\n{(first['expected_output'] or '').strip()}\nYour output:\n{first['stdout'].strip()}"
    elif first["stderr"].strip():
        detail += f"\nError:\n{first['stderr'].strip()[-600:]}"
    return detail


def grade_code(sub: dict, backend: str | None, want_fix: bool) -> tuple[dict, list[str]]:
    """Grade one code submission. Returns (graded result, error messages)."""
    errors: list[str] = []
    language = sub.get("language") or "python"
    code = sub.get("student_answer") or ""
    tests = sub.get("tests") or []
    graded = {
        "question": sub.get("question", ""),
        "student_answer": code,
        "correct_answer": "",
        "is_correct": False,
        "bloom_level": sub.get("bloom_level"),
        "feedback": "",
        "tests_passed": 0,
        "tests_total": len(tests),
        "code_result": None,
        "suggestion": None,
    }
    if not tests:
        graded["feedback"] = "This question has no test cases, so it cannot be graded."
        return graded, errors
    try:
        result = execute(language, code, tests)
    except (ValueError, RunnerError) as exc:
        graded["feedback"] = f"Your code could not be run: {exc}"
        errors.append(f"assessment_agent.grade: {exc}")
        return graded, errors

    graded.update(
        is_correct=result["status"] == "passed",
        feedback=_feedback(result),
        tests_passed=result["passed"],
        code_result=redact_hidden(result),
    )
    if want_fix and not graded["is_correct"]:
        try:
            graded["suggestion"] = suggest_fix(
                language, code, result, tests, problem=sub.get("question"), backend=backend
            )
        except llm_client.LLMError as exc:
            errors.append(f"assessment_agent.grade: fix suggestion unavailable ({exc})")
    return graded, errors
