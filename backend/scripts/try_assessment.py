"""Run the Assessment Agent directly (no server) and print the result or full traceback.
Usage (from backend/):  python scripts\try_assessment.py [ollama|gemini|openrouter]
"""
import json
import sys
import traceback

sys.path.insert(0, ".")
from app.agents import assessment_agent  # noqa: E402

backend = sys.argv[1] if len(sys.argv) > 1 else "gemini"
state = {
    "course_id": "CS301-sample",
    "quiz_topic": "deadlocks",
    "bloom_level": "mixed",
    "num_questions": 4,
    "llm_backend": backend,
}
try:
    out = assessment_agent.run(state)
    print(json.dumps(out.get("generated_quiz"), indent=2))
    print("ERRORS:", out.get("errors"))
except Exception:
    traceback.print_exc()
