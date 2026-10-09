"""Sandbox-side harness: compiles and runs one submission against test inputs.

This file runs INSIDE the code-runner container (or directly on this machine
in "local" dev mode), so it uses the standard library only. It reads
`job.json` from the current directory, copies the source file into a private
temp directory, compiles it if the language needs that, runs it once per test
input with a time limit, and prints exactly one JSON object to stdout.

It never sees expected outputs: comparing results happens on the host in
`code_runner.py`, so nothing secret is ever inside the sandbox.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

# Some machines inject JVM options and Java prints a notice about them on
# stderr; that is noise for students, so drop those lines.
NOISE = ("Picked up JAVA_TOOL_OPTIONS", "Picked up _JAVA_OPTIONS", "Picked up JDK_JAVA_OPTIONS")


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _clean(value, limit):
    text = "".join(
        line for line in _text(value).splitlines(keepends=True) if not line.startswith(NOISE)
    )
    if len(text) > limit:
        return text[:limit] + "\n...[output truncated]"
    return text


def _run(cmd, cwd, stdin, timeout, limit, env=None):
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            input=(stdin or "").encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        code, out, err, timed_out = proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as exc:
        code, out, err, timed_out = None, exc.stdout, exc.stderr, True
    return {
        "exit_code": code,
        "stdout": _clean(out, limit),
        "stderr": _clean(err, limit),
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - start) * 1000),
    }


def _plan(language, source_file, work):
    """Return (required tools, compile command or None, run command, extra seconds)."""
    exe = "main.exe" if os.name == "nt" else "main"
    if language == "python":
        return (
            [],
            [sys.executable, "-m", "py_compile", source_file],
            [sys.executable, "-I", source_file],
            0.0,
        )
    if language == "c":
        return (
            ["gcc"],
            ["gcc", "-O2", "-std=c11", "-o", exe, source_file, "-lm"],
            [os.path.join(work, exe)],
            0.0,
        )
    if language == "java":
        class_name = source_file[: -len(".java")]
        return (
            ["javac", "java"],
            ["javac", "-encoding", "UTF-8", "-J-Xmx256m", source_file],
            ["java", "-Xmx256m", "-Xss16m", "-cp", ".", class_name],
            2.0,  # JVM start-up time should not count against the student
        )
    return None


def main():
    job = json.load(open("job.json", encoding="utf-8"))
    language = job["language"]
    source_file = job["source_file"]
    limit = int(job.get("max_output", 10000))
    time_limit = float(job.get("time_limit", 2.0))
    compile_timeout = float(job.get("compile_timeout", 30))

    work = tempfile.mkdtemp(prefix="run_")
    try:
        shutil.copy(source_file, os.path.join(work, source_file))
        plan = _plan(language, source_file, work)
        if plan is None:
            print(json.dumps({"status": "unsupported", "message": f"Unsupported language {language!r}."}))
            return
        tools, compile_cmd, run_cmd, extra = plan
        missing = [t for t in tools if shutil.which(t) is None]
        if missing:
            print(json.dumps({
                "status": "unsupported",
                "message": f"{', '.join(missing)} is not installed on the code runner.",
            }))
            return

        # Plain "C" locale: compilers then quote with ' instead of curly quotes,
        # which some terminals (e.g. Windows PowerShell) display as garbage.
        compile_env = dict(os.environ, LC_ALL="C", LANG="C")
        compiled = _run(compile_cmd, work, "", compile_timeout, limit, env=compile_env)
        if compiled["timed_out"] or compiled["exit_code"] != 0:
            message = compiled["stderr"] or compiled["stdout"] or "Compilation timed out."
            print(json.dumps({"status": "compile_error", "compile_output": message}))
            return

        results = [
            _run(run_cmd, work, test.get("stdin", ""), time_limit + extra, limit)
            for test in job.get("tests") or [{"stdin": ""}]
        ]
        print(json.dumps({
            "status": "ok",
            "compile_output": compiled["stderr"],
            "tests": results,
        }))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # report, never crash silently
        print(json.dumps({"status": "internal_error", "message": f"{type(exc).__name__}: {exc}"}))
