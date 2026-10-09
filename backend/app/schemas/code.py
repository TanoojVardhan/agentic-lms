"""Schemas for the code playground (`/api/v1/code`), which backs the
frontend's separate code-block section."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Language = Literal["python", "c", "java"]


class FixSuggestion(BaseModel):
    explanation: str
    corrected_code: Optional[str] = None
    verified: Optional[bool] = Field(
        default=None,
        description="True if the suggested code was run and worked; None if it could not be checked",
    )


class CodeRunRequest(BaseModel):
    language: Language
    code: str = Field(..., min_length=1, max_length=50_000)
    stdin: str = ""
    expected_output: Optional[str] = Field(
        default=None, description="Optional: compare the output against this"
    )
    suggest_fix: bool = True
    llm_backend: Optional[str] = None


class CodeRunResponse(BaseModel):
    status: str  # passed | ok | wrong_answer | runtime_error | timeout | compile_error
    compile_output: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    suggestion: Optional[FixSuggestion] = None
    suggestion_error: Optional[str] = None


class LanguageInfo(BaseModel):
    id: str
    name: str
    template: str


class LanguagesResponse(BaseModel):
    languages: List[LanguageInfo]
    time_limit_s: float
