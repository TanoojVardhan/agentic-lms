"""Code playground API: run Python, C or Java and get errors plus a suggested
fix. This is what the frontend's separate code-block section will call."""
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.code import (
    CodeRunRequest,
    CodeRunResponse,
    FixSuggestion,
    LanguageInfo,
    LanguagesResponse,
)
from app.tools.code_assistant import suggest_fix
from app.tools.code_runner import RunnerError, execute
from app.tools.llm_client import LLMError

router = APIRouter(prefix="/code", tags=["code"])

TEMPLATES = [
    LanguageInfo(
        id="python",
        name="Python 3",
        template="def main():\n    data = input()\n    print(data)\n\n\nif __name__ == \"__main__\":\n    main()\n",
    ),
    LanguageInfo(
        id="c",
        name="C (gcc, C11)",
        template="#include <stdio.h>\n\nint main(void) {\n    int n;\n    scanf(\"%d\", &n);\n    printf(\"%d\\n\", n);\n    return 0;\n}\n",
    ),
    LanguageInfo(
        id="java",
        name="Java 17",
        template="import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner in = new Scanner(System.in);\n        int n = in.nextInt();\n        System.out.println(n);\n    }\n}\n",
    ),
]


@router.get("/languages", response_model=LanguagesResponse)
async def languages():
    """Supported languages with starter code for the editor."""
    return LanguagesResponse(languages=TEMPLATES, time_limit_s=settings.code_time_limit_s)


@router.post("/run", response_model=CodeRunResponse)
def run_code(req: CodeRunRequest):
    """Run code once with the given stdin. On a compile error, crash, timeout or
    (when expected_output is given) wrong output, also returns a suggested fix."""
    tests = [{"stdin": req.stdin, "expected_output": req.expected_output}]
    try:
        result = execute(req.language, req.code, tests)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RunnerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    run = result["tests"][0] if result["tests"] else {}
    response = CodeRunResponse(
        status=result["status"],
        compile_output=result["compile_output"],
        stdout=run.get("stdout", ""),
        stderr=run.get("stderr", ""),
        exit_code=run.get("exit_code"),
        duration_ms=run.get("duration_ms"),
    )
    if req.suggest_fix and result["status"] not in ("passed", "ok"):
        try:
            response.suggestion = FixSuggestion(
                **suggest_fix(req.language, req.code, result, tests, backend=req.llm_backend)
            )
        except LLMError as exc:
            response.suggestion_error = str(exc)
    return response
