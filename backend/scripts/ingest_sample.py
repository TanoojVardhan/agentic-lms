"""One-off script: ingest the sample syllabus into ChromaDB under a test
course_id, so the Tutor Agent has something real to retrieve against before
any real Moodle course content exists.

Run from the `backend/` directory so the `app` package resolves:
    python scripts/ingest_sample.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.vector_store import ingest_document  # noqa: E402

SAMPLE_COURSE_ID = "CS301-sample"


def main():
    sample_path = Path(__file__).resolve().parent.parent / "data" / "sample_syllabus.txt"
    text = sample_path.read_text(encoding="utf-8")

    print(f"Ingesting {sample_path.name} into course_id={SAMPLE_COURSE_ID} ...")
    n_chunks = ingest_document(
        course_id=SAMPLE_COURSE_ID,
        text=text,
        source_name=sample_path.name,
    )
    print(f"Done — {n_chunks} chunks stored.")
    print(f"Try: POST /api/v1/tutor/ask with course_id='{SAMPLE_COURSE_ID}'")


if __name__ == "__main__":
    main()
