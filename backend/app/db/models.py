"""Tables for quizzes and student results.

quizzes ─┬─ quiz_questions   (full question incl. answers/hidden tests, server-side only)
         └─ attempts ── attempt_answers   (one row per answered question)

attempt_answers keeps topic, Bloom level and question type on every row so the
Mentor Agent can find weak areas with simple queries.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String(100), index=True)
    topic: Mapped[str] = mapped_column(String(300))
    question_type: Mapped[str] = mapped_column(String(20))
    bloom_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    questions: Mapped[list["QuizQuestionRow"]] = relationship(
        back_populates="quiz", order_by="QuizQuestionRow.position", cascade="all, delete-orphan"
    )


class QuizQuestionRow(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON)  # the full generated question

    quiz: Mapped[Quiz] = relationship(back_populates="questions")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"), index=True)
    student_id: Mapped[str] = mapped_column(String(100), index=True)
    course_id: Mapped[str] = mapped_column(String(100), index=True)
    score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    percentage: Mapped[float] = mapped_column(Float)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    answers: Mapped[list["AttemptAnswer"]] = relationship(
        back_populates="attempt", order_by="AttemptAnswer.position", cascade="all, delete-orphan"
    )


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("quiz_questions.id"))
    position: Mapped[int] = mapped_column(Integer)
    student_id: Mapped[str] = mapped_column(String(100), index=True)
    course_id: Mapped[str] = mapped_column(String(100), index=True)
    topic: Mapped[str] = mapped_column(String(300))
    question_type: Mapped[str] = mapped_column(String(20))
    bloom_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    student_answer: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    tests_passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # full graded result

    attempt: Mapped[Attempt] = relationship(back_populates="answers")
