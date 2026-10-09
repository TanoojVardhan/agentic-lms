"""Ingest a real syllabus PDF into ChromaDB under a chosen course_id.

Usage (run from the `backend/` directory so the `app` package resolves):
    python scripts/ingest_pdf.py path/to/syllabus.pdf COURSE_ID

Example:
    python scripts/ingest_pdf.py data/CS301_syllabus.pdf CS301-real
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.vector_store import ingest_document  # noqa: E402


def extract_text(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages_text = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(text)
        else:
            print(f"  [warn] page {i + 1} had no extractable text (scanned image? needs OCR)")
    return "\n\n".join(pages_text)


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/ingest_pdf.py <path_to_pdf> <course_id>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1]).resolve()
    course_id = sys.argv[2]

    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    print(f"Extracting text from {pdf_path.name} ...")
    text = extract_text(pdf_path)

    if not text.strip():
        print("No text could be extracted — this PDF may be scanned images, which need OCR first.")
        sys.exit(1)

    print(f"Extracted {len(text)} characters. Ingesting into course_id={course_id!r} ...")
    n_chunks = ingest_document(
        course_id=course_id,
        text=text,
        source_name=pdf_path.name,
    )
    print(f"Done — {n_chunks} chunks stored.")
    print(f"Try: POST /api/v1/tutor/ask with course_id='{course_id}'")


if __name__ == "__main__":
    main()
