"""LLM help for failed code: explain the problem and suggest corrected code.

The suggestion is then run through the same code runner, so the response can
say whether the suggested fix actually works (`verified`) instead of trusting
the model blindly.
"""
from __future__ import annotations

import json
import re

from app.tools import llm_client
from app.tools.code_runner import RunnerError, execute

FIX_SYSTEM_PROMPT = (
    "You are a patient programming tutor. A student's program failed. Explain "
    "in 2-4 short sentences what is wrong and why, then give the corrected "
    "program. Keep the student's approach, structure and variable names; "
    "change only what is needed. Use the same programming language. "
    'Respond with ONLY a JSON object: {"explanation": str, "corrected_code": str}. '
    "No markdown fences, no text outside the JSON."
)


def _describe_failure(result: dict) -> str:
    if result.get("status") == "compile_error":
        return "It does not compile. Compiler output:\n" + (result.get("compile_output") or "")[:2000]
    lines = []
    failing = [t for t in result.get("tests", []) if t["verdict"] not in ("passed", "ran")]
    for t in failing[:3]:
        lines.append(
            f"- Verdict: {t['verdict']}\n"
            f"  Input:\n{(t.get('stdin') or '')[:500]}\n"
            f"  Expected output:\n{(t.get('expected_output') or '(not given)')[:500]}\n"
            f"  Actual output:\n{(t.get('stdout') or '')[:500]}\n"
            f"  Error output:\n{(t.get('stderr') or '')[:800]}"
        )
    return "It ran but failed these tests:\n" + "\n".join(lines)


def _parse_suggestion(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1], strict=False)
            if isinstance(data, dict) and data.get("corrected_code"):
                return {
                    "explanation": str(data.get("explanation") or "").strip(),
                    "corrected_code": str(data["corrected_code"]),
                }
        except json.JSONDecodeError:
            pass
    # Fallback: the model answered in prose with a code block.
    block = re.search(r"```[a-zA-Z0-9+]*\n(.*?)```", raw, re.DOTALL)
    if block:
        return {
            "explanation": raw[: block.start()].strip()[:1500],
            "corrected_code": block.group(1),
        }
    return {"explanation": raw.strip()[:1500], "corrected_code": None}


def suggest_fix(language: str, code: str, result: dict, tests: list[dict] | None = None,
                problem: str | None = None, backend: str | None = None) -> dict:
    """Ask the LLM for a fix, then run the fix to see whether it works.

    Returns {"explanation", "corrected_code", "verified"} where verified is True
    if the fix compiles and passes every test that has an expected output (or
    simply runs without errors when there is nothing to compare), False if it
    still fails, and None if it could not be checked. Raises llm_client.LLMError
    if the LLM is unavailable.
    """
    prompt = (
        f"Language: {language}\n\n"
        + (f"Problem:\n{problem}\n\n" if problem else "")
        + f"Student code:\n{code}\n\n"
        + f"What went wrong:\n{_describe_failure(result)}\n\n"
        + "Return the JSON object only."
    )
    raw = llm_client.generate(prompt, backend=backend, system=FIX_SYSTEM_PROMPT)
    suggestion = _parse_suggestion(raw)
    suggestion["verified"] = None
    if suggestion["corrected_code"]:
        try:
            check = execute(language, suggestion["corrected_code"], tests or [{"stdin": ""}])
            suggestion["verified"] = check["status"] in ("passed", "ok")
        except (RunnerError, ValueError):
            suggestion["verified"] = None
    return suggestion
