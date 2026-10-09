"""Pydantic schemas for the Assessment Agent (generation and grading)."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class QuizGenerateRequest(BaseModel):
    course_id: str
    topic: str = Field(..., description="Topic/concept to quiz on, e.g. 'deadlocks'")
    bloom_level: Optional[str] = Field(
        default="mixed",
        description="One of: remember, understand, apply, analyze, evaluate, create, or 'mixed'",
    )
    num_questions: int = Field(default=5, ge=1, le=15)
    llm_backend: Optional[str] = None
    question_type: Literal["mcq", "numeric", "code"] = "mcq"
    seed: Optional[int] = Field(
        default=None, description="Numeric only: same seed gives the same numbers (e.g. per student)"
    )
    include_answers: bool = Field(
        default=False,
        description="Faculty/testing view: include answers, explanations, hidden tests and reference solutions",
    )
    created_by: Optional[str] = None  # faculty id, optional


class CodeTest(BaseModel):
    stdin: str = ""
    expected_output: Optional[str] = None
    hidden: bool = False  # hidden tests are graded but never shown to students


class QuizQuestion(BaseModel):
    id: Optional[str] = None  # set once the quiz is saved; students answer by this id
    question: str
    options: List[str] = []  # empty for numeric questions
    correct_answer: Optional[str] = None  # hidden from students
    bloom_level: Optional[str] = None
    explanation: Optional[str] = None  # hidden from students
    question_type: str = "mcq"
    tolerance: Optional[float] = None  # numeric only
    # code only
    tests: Optional[List[CodeTest]] = None
    reference_solution: Optional[str] = None  # for faculty; never show to students
    languages: Optional[List[str]] = None


class QuizGenerateResponse(BaseModel):
    quiz_id: Optional[str] = None  # None if nothing could be generated
    topic: str
    questions: List[QuizQuestion]
    warnings: List[str] = []  # e.g. fewer questions than requested, no course material


# ---- Grading ----

class SubmittedAnswer(BaseModel):
    question: str
    options: List[str] = []
    correct_answer: str
    question_type: str = "mcq"
    tolerance: Optional[float] = None
    student_answer: str = Field(
        ..., description="MCQ: option text or letter (A-D). Numeric: the number. Code: the source code."
    )
    language: Optional[str] = None  # code only: python | c | java
    tests: Optional[List[CodeTest]] = None  # code only
    bloom_level: Optional[str] = None
    explanation: Optional[str] = None  # fallback if AI feedback is unavailable


class QuizGradeRequest(BaseModel):
    course_id: str
    submissions: List[SubmittedAnswer] = Field(..., min_length=1)
    llm_backend: Optional[str] = None
    suggest_fix: bool = True  # code questions: include an LLM-suggested fix on failure


class GradedQuestion(BaseModel):
    question_id: Optional[str] = None
    question: str
    student_answer: str
    correct_answer: str
    is_correct: bool
    bloom_level: Optional[str] = None
    feedback: str
    # code only
    tests_passed: Optional[int] = None
    tests_total: Optional[int] = None
    code_result: Optional[Dict[str, Any]] = None  # per-test verdicts; hidden tests redacted
    suggestion: Optional[Dict[str, Any]] = None  # {explanation, corrected_code, verified}


class QuizGradeResponse(BaseModel):
    score: int
    total: int
    percentage: float
    results: List[GradedQuestion]


# ---- Stored quizzes ----

class QuizView(BaseModel):
    quiz_id: str
    course_id: str
    topic: str
    question_type: str
    created_at: str
    questions: List[QuizQuestion]


class AnswerIn(BaseModel):
    question_id: str
    student_answer: str = ""  # MCQ option text or letter, a number, or source code
    language: Optional[Literal["python", "c", "java"]] = None  # code questions only


class QuizSubmitRequest(BaseModel):
    student_id: str = Field(..., min_length=1)
    answers: List[AnswerIn]
    llm_backend: Optional[str] = None
    suggest_fix: bool = True


class QuizSubmitResponse(BaseModel):
    attempt_id: str
    quiz_id: str
    student_id: str
    score: int
    total: int
    percentage: float
    results: List[GradedQuestion]
    warnings: List[str] = []


class StatRow(BaseModel):
    name: str
    correct: int
    total: int
    accuracy: float


class StudentPerformance(BaseModel):
    student_id: str
    course_id: Optional[str] = None
    questions_answered: int
    overall_accuracy: Optional[float] = None
    by_topic: List[StatRow]
    by_bloom_level: List[StatRow]
    by_question_type: List[StatRow]
    weak_topics: List[str]  # topics under 60% accuracy, weakest first
    recent_attempts: List[Dict[str, Any]]
