"""Runs student code (Python, C or Java) against test inputs.

Two executors, picked by CODE_RUNNER_MODE in backend/.env:

- "docker" (default): every run happens in a throwaway container built from
  backend/sandbox/Dockerfile, with no network, a read-only filesystem, capped
  memory, CPU and process count, no Linux capabilities, and a time limit.
  Build the image once:  docker build -t agentic-lms-runner backend/sandbox
- "local": runs on this machine with whatever compilers are installed.
  For development and automated tests only, because student code is NOT
  isolated from your computer in this mode.

Tests use the standard judge format: each test gives `stdin` and (usually)
an `expected_output`; outputs are compared token by token, with a small
tolerance for real numbers, so extra spaces or 0.5 vs 0.50 don't fail a
correct answer.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from app.config import settings

HARNESS = Path(__file__).with_name("code_harness.py")
SUPPORTED_LANGUAGES = ("python", "c", "java")
_ALIASES = {"py": "python", "python3": "python"}
MAX_CODE_CHARS = 50_000
MAX_TESTS = 20
COMPILE_TIMEOUT_S = 30


# Crashes by signal give no error text; explain the common ones for students.
_CRASHES = {
    -11: "Segmentation fault: the program accessed invalid memory (e.g. a bad pointer or array index).",
    139: "Segmentation fault: the program accessed invalid memory (e.g. a bad pointer or array index).",
    -8: "Arithmetic error: for example an integer division by zero.",
    136: "Arithmetic error: for example an integer division by zero.",
    -6: "The program aborted (e.g. a failed assertion or memory corruption).",
    -9: "The program was killed, probably for using too much memory.",
    137: "The program was killed, probably for using too much memory.",
    3221225477: "Access violation: the program accessed invalid memory.",
    3221225620: "Arithmetic error: for example an integer division by zero.",
}


class RunnerError(RuntimeError):
    """The runner itself could not run the code (Docker missing, image not built...)."""


def normalize_language(language: str) -> str:
    lang = (language or "").strip().lower()
    lang = _ALIASES.get(lang, lang)
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language {language!r}. Use python, c or java.")
    return lang


def _source_file(language: str, code: str) -> str:
    if language == "python":
        return "main.py"
    if language == "c":
        return "main.c"
    # Java: the file name must match the public class name.
    match = re.search(r"public\s+(?:final\s+|abstract\s+)*class\s+([A-Za-z_]\w*)", code)
    return f"{match.group(1) if match else 'Main'}.java"


def outputs_match(actual: str, expected: str, rel_tol: float = 1e-4) -> bool:
    """Token-by-token comparison; numbers may differ by a tiny tolerance."""
    a, e = (actual or "").split(), (expected or "").split()
    if len(a) != len(e):
        return False
    for x, y in zip(a, e):
        if x == y:
            continue
        try:
            fx, fy = float(x), float(y)
        except ValueError:
            return False
        if abs(fx - fy) > max(rel_tol * max(abs(fx), abs(fy)), 1e-6):
            return False
    return True


def execute(language: str, code: str, tests: list[dict] | None = None,
            time_limit: float | None = None) -> dict:
    """Compile and run `code` once per test.

    tests: [{"stdin": str, "expected_output": str | None, "hidden": bool}]
    Returns {"status", "compile_output", "tests": [...], "passed", "total"} where
    status is one of: passed, ok (ran, nothing to compare), wrong_answer,
    runtime_error, timeout, compile_error.
    Raises ValueError for bad input and RunnerError if the runner is unavailable.
    """
    lang = normalize_language(language)
    if not code or not code.strip():
        raise ValueError("Code is empty.")
    if len(code) > MAX_CODE_CHARS:
        raise ValueError(f"Code is too long (max {MAX_CODE_CHARS} characters).")
    tests = list(tests or [{"stdin": ""}])[:MAX_TESTS]
    limit = float(time_limit or settings.code_time_limit_s)
    source = _source_file(lang, code)
    job = {
        "language": lang,
        "source_file": source,
        "tests": [{"stdin": t.get("stdin") or ""} for t in tests],
        "time_limit": limit,
        "compile_timeout": COMPILE_TIMEOUT_S,
        "max_output": 10_000,
    }
    budget = COMPILE_TIMEOUT_S + len(tests) * (limit + 3) + 20

    with tempfile.TemporaryDirectory(prefix="agentic_run_") as tmp:
        folder = Path(tmp)
        (folder / source).write_text(code, encoding="utf-8")
        (folder / "job.json").write_text(json.dumps(job), encoding="utf-8")
        shutil.copy(HARNESS, folder / "harness.py")
        # The sandbox runs as an unprivileged user; on Linux/macOS hosts it
        # needs read access to these files (Docker Desktop on Windows ignores this).
        os.chmod(folder, 0o755)
        for f in folder.iterdir():
            os.chmod(f, 0o644)
        if settings.code_runner_mode == "local":
            raw = _run_local(folder, budget)
        else:
            raw = _run_docker(folder, budget)
    return _verdicts(raw, tests)


def _run_local(folder: Path, budget: float) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, "harness.py"], cwd=folder, capture_output=True, timeout=budget
        )
    except subprocess.TimeoutExpired as exc:
        raise RunnerError("The code runner timed out.") from exc
    return _parse(proc)


def _run_docker(folder: Path, budget: float) -> dict:
    name = f"agentic-run-{uuid.uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--memory", "512m", "--memory-swap", "512m",
        "--cpus", "1", "--pids-limit", "128",
        "--read-only", "--tmpfs", "/tmp:rw,exec,size=64m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--mount", f"type=bind,source={folder},target=/code,readonly",
        "-w", "/code",
        settings.code_runner_image, "python3", "harness.py",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=budget)
    except FileNotFoundError as exc:
        raise RunnerError(
            "Docker is not installed or not on PATH. Start Docker Desktop, or set "
            "CODE_RUNNER_MODE=local in backend/.env for development."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        subprocess.run(["docker", "kill", name], capture_output=True)
        raise RunnerError("The code runner timed out.") from exc
    return _parse(proc)


def _parse(proc: subprocess.CompletedProcess) -> dict:
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    err = proc.stderr.decode("utf-8", errors="replace")
    try:
        return json.loads(out.splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        pass
    low = err.lower()
    image = settings.code_runner_image
    if "unable to find image" in low or "pull access denied" in low:
        raise RunnerError(
            f"Code runner image {image!r} is not built yet. Build it once with: "
            f"docker build -t {image} backend/sandbox"
        )
    if "docker daemon" in low or "error during connect" in low or "cannot connect" in low:
        raise RunnerError("Docker is not running. Start Docker Desktop and try again.")
    raise RunnerError(f"Code runner failed: {(err or out)[-500:]}")


def _verdicts(raw: dict, tests: list[dict]) -> dict:
    status = raw.get("status")
    if status in ("unsupported", "internal_error"):
        raise RunnerError(raw.get("message", "Code runner error."))
    if status == "compile_error":
        return {
            "status": "compile_error",
            "compile_output": raw.get("compile_output", ""),
            "tests": [],
            "passed": 0,
            "total": len(tests),
        }

    results, passed = [], 0
    for test, run in zip(tests, raw.get("tests", [])):
        expected = test.get("expected_output")
        if run["timed_out"]:
            verdict = "timeout"
        elif run["exit_code"] != 0:
            verdict = "runtime_error"
            if not run["stderr"].strip():
                run["stderr"] = _CRASHES.get(
                    run["exit_code"], f"The program exited with code {run['exit_code']}."
                )
        elif expected is None:
            verdict = "ran"
        else:
            verdict = "passed" if outputs_match(run["stdout"], expected) else "wrong_answer"
        passed += verdict == "passed"
        results.append({
            "verdict": verdict,
            "stdin": test.get("stdin") or "",
            "expected_output": expected,
            "stdout": run["stdout"],
            "stderr": run["stderr"],
            "exit_code": run["exit_code"],
            "duration_ms": run["duration_ms"],
            "hidden": bool(test.get("hidden")),
        })

    verdicts = {r["verdict"] for r in results}
    for overall in ("runtime_error", "timeout", "wrong_answer"):
        if overall in verdicts:
            break
    else:
        overall = "passed" if "passed" in verdicts else "ok"
    return {
        "status": overall,
        "compile_output": raw.get("compile_output", ""),
        "tests": results,
        "passed": passed,
        "total": len(results),
    }


def redact_hidden(result: dict) -> dict:
    """Copy of a result that is safe to show students: hidden tests keep only
    their verdict and timing, never their input, expected output or output."""
    safe = dict(result)
    safe["tests"] = [
        {k: (None if t.get("hidden") and k in ("stdin", "expected_output", "stdout", "stderr") else v)
         for k, v in t.items()}
        for t in result.get("tests", [])
    ]
    return safe
