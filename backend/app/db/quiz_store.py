"""Saving quizzes, grading stored quizzes, and summarizing student results.

The full question (correct answer, explanation, hidden tests, reference
solution) never leaves the server: students receive `public_question()`
copies, submit answers by question id, and grading looks the answers up here.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.agents import assessment_agent
from app.db.database import get_session
from app.db.models import Attempt, AttemptAnswer, Quiz, QuizQuestionRow

# Keys only the server (or faculty) may see.
_PRIVATE_KEYS = ("correct_answer", "explanation", "reference_solution", "tolerance")


class NotFound(LookupError):
    pass


def public_question(data: dict, question_id: str) -> dict:
    """Student-safe copy: no answers, no explanations, only visible tests."""
    safe = {k: v for k, v in data.items() if k not in _PRIVATE_KEYS}
    safe["id"] = question_id
    if data.get("tests") is not None:
        safe["tests"] = [t for t in data["tests"] if not t.get("hidden")]
    return safe


def save_quiz(course_id: str, topic: str, question_type: str, bloom_level: str | None,
              questions: list[dict], created_by: str | None = None) -> tuple[str, list[str]]:
    with get_session() as db:
        quiz = Quiz(course_id=course_id, topic=topic, question_type=question_type,
                    bloom_level=bloom_level, created_by=created_by)
        quiz.questions = [
            QuizQuestionRow(position=i, question_type=q.get("question_type", "mcq"), data=q)
            for i, q in enumerate(questions)
        ]
        db.add(quiz)
        db.commit()
        return quiz.id, [row.id for row in quiz.questions]


def get_quiz(quiz_id: str, include_answers: bool = False) -> dict:
    with get_session() as db:
        quiz = db.get(Quiz, quiz_id)
        if quiz is None:
            raise NotFound(f"Quiz {quiz_id!r} not found.")
        return {
            "quiz_id": quiz.id,
            "course_id": quiz.course_id,
            "topic": quiz.topic,
            "question_type": quiz.question_type,
            "created_at": quiz.created_at.isoformat(),
            "questions": [
                ({**row.data, "id": row.id} if include_answers else public_question(row.data, row.id))
                for row in quiz.questions
            ],
        }


def submit_attempt(quiz_id: str, student_id: str, answers: list[dict],
                   llm_backend: str | None = None, suggest_fix: bool = True) -> dict:
    """Grade a student's answers against the stored quiz and save the attempt.

    answers: [{"question_id", "student_answer", "language"?}]. Questions the
    student skipped count as wrong. Unknown question ids raise ValueError.
    """
    with get_session() as db:
        quiz = db.get(Quiz, quiz_id)
        if quiz is None:
            raise NotFound(f"Quiz {quiz_id!r} not found.")
        rows = list(quiz.questions)
        by_id = {a["question_id"]: a for a in answers}
        unknown = set(by_id) - {r.id for r in rows}
        if unknown:
            raise ValueError(f"Unknown question id(s) for this quiz: {sorted(unknown)}")

        submissions = []
        for row in rows:
            given = by_id.get(row.id, {})
            sub = dict(row.data)
            sub["student_answer"] = given.get("student_answer") or ""
            if row.question_type == "code":
                sub["language"] = given.get("language") or "python"
            submissions.append(sub)

        graded_state = assessment_agent.grade({
            "course_id": quiz.course_id,
            "submissions": submissions,
            "llm_backend": llm_backend,
            "suggest_fix": suggest_fix,
        })
        evaluation = graded_state["evaluation_result"]

        attempt = Attempt(
            quiz_id=quiz.id, student_id=student_id, course_id=quiz.course_id,
            score=evaluation["score"], total=evaluation["total"],
            percentage=evaluation["percentage"],
        )
        results = []
        for row, sub, graded in zip(rows, submissions, evaluation["results"]):
            graded = {**graded, "question_id": row.id}
            if row.question_type == "code":
                graded["correct_answer"] = ""  # never reveal the reference solution
            results.append(graded)
            attempt.answers.append(AttemptAnswer(
                question_id=row.id, position=row.position, student_id=student_id,
                course_id=quiz.course_id, topic=quiz.topic, question_type=row.question_type,
                bloom_level=graded.get("bloom_level") or row.data.get("bloom_level"),
                student_answer=sub["student_answer"], language=sub.get("language"),
                is_correct=bool(graded["is_correct"]),
                tests_passed=graded.get("tests_passed"), tests_total=graded.get("tests_total"),
                feedback=graded.get("feedback") or "", result=graded,
            ))
        db.add(attempt)
        db.commit()
        return {
            "attempt_id": attempt.id,
            "quiz_id": quiz.id,
            "student_id": student_id,
            "score": attempt.score,
            "total": attempt.total,
            "percentage": attempt.percentage,
            "results": results,
            "warnings": graded_state.get("errors") or [],
        }


def _summary(rows: list[AttemptAnswer], key) -> list[dict]:
    buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        name = key(r) or "unknown"
        buckets[name][0] += int(r.is_correct)
        buckets[name][1] += 1
    out = [
        {"name": k, "correct": c, "total": t, "accuracy": round(100 * c / t, 1)}
        for k, (c, t) in buckets.items()
    ]
    return sorted(out, key=lambda x: (x["accuracy"], -x["total"]))


def student_performance(student_id: str, course_id: str | None = None) -> dict:
    """Accuracy overall and by topic, Bloom level and question type (weakest first).
    This is the input the Mentor Agent uses to find knowledge gaps."""
    with get_session() as db:
        q = select(AttemptAnswer).where(AttemptAnswer.student_id == student_id)
        a = select(Attempt).where(Attempt.student_id == student_id)
        if course_id:
            q = q.where(AttemptAnswer.course_id == course_id)
            a = a.where(Attempt.course_id == course_id)
        rows = list(db.scalars(q))
        attempts = list(db.scalars(a.order_by(Attempt.submitted_at.desc()).limit(20)))
        quiz_topics = {
            quiz.id: quiz.topic
            for quiz in db.scalars(select(Quiz).where(Quiz.id.in_({x.quiz_id for x in attempts})))
        } if attempts else {}

    correct = sum(int(r.is_correct) for r in rows)
    by_topic = _summary(rows, lambda r: r.topic)
    return {
        "student_id": student_id,
        "course_id": course_id,
        "questions_answered": len(rows),
        "overall_accuracy": round(100 * correct / len(rows), 1) if rows else None,
        "by_topic": by_topic,
        "by_bloom_level": _summary(rows, lambda r: r.bloom_level),
        "by_question_type": _summary(rows, lambda r: r.question_type),
        "weak_topics": [t["name"] for t in by_topic if t["accuracy"] < 60],
        "recent_attempts": [
            {
                "attempt_id": x.id, "quiz_id": x.quiz_id, "topic": quiz_topics.get(x.quiz_id),
                "score": x.score, "total": x.total, "percentage": x.percentage,
                "submitted_at": x.submitted_at.isoformat(),
            }
            for x in attempts
        ],
    }
