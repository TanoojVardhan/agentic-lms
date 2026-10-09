# CLAUDE.md — Agentic LMS development guidelines

## Project decisions (locked in during ideation — do not silently change these)
- Agent orchestration: **LangGraph** (not CrewAI/AutoGen)
- LLM backends: **Ollama, OpenRouter, Gemini only — never OpenAI or Anthropic API calls** (cost constraint)
  - Default backend set via `DEFAULT_LLM_BACKEND` in `.env`, routed through `app/tools/llm_client.py`
- Backend: Python + FastAPI, async throughout
- Database: Postgres, hosted on a shared cloud provider (not local) so both team members see the same app data
- Moodle: local Docker instance per person (not shared) — kept consistent across machines via a shared seed script (`moodle_seed/`, not yet built)
- Moodle integration: REST API first (`app/tools/moodle_client.py`); a custom plugin is added later ONLY for write-back actions the REST API can't do (e.g. pushing a generated quiz into a course) — do not build a full plugin upfront
- All 4 agents are being built (no scope-cut to 2) — Tutor, Assessment, Mentor, Faculty Copilot
- Build order: **backend fully working first, then the Next.js frontend** — do not start frontend work before backend agents function end-to-end via API calls
- Frontend: Next.js, built after backend

## Architecture enforcement
- Agents live in `backend/app/agents/`, each exposing a `run(state: AgentState) -> AgentState` function, and are wired as LangGraph nodes in `backend/app/core/graph.py`. Never bypass the shared `AgentState` (`backend/app/core/state.py`) by passing ad-hoc dicts between agents.
- All outbound Moodle calls go through `MoodleClient` in `backend/app/tools/moodle_client.py` — no raw `httpx` calls to Moodle elsewhere.
- All LLM calls go through `generate()` in `backend/app/tools/llm_client.py` — never instantiate an Ollama/OpenRouter/Gemini client directly inside an agent file.

## Coding standards
- Async (`async def`) for all I/O-bound backend code.
- Pydantic v2 schemas for all API request/response models (`backend/app/schemas/`).
- Every new agent capability gets a corresponding test in `backend/tests/`.

## Current state (update this as work progresses)
- [x] Repo skeleton, FastAPI app, LangGraph state/graph wiring (stubs), Moodle REST client, 4 agent stubs
- [x] Docker installed and verified (Docker Desktop, v29.8.1 + Compose v5.5.1)
- [x] Ollama installed and verified (v0.20.6, llama3.1 + llama2 available)
- [x] Local Moodle instance running via Docker (bitnamilegacy/moodle, since bitnami/moodle requires a paid plan now)
- [x] ChromaDB ingestion pipeline for Tutor Agent (Ollama embeddings, not sentence-transformers/torch — see note below)
- [x] Assessment Agent: Bloom's MCQs, numeric questions, code questions (Python/C/Java) + grading
- [x] Code runner + `/api/v1/code` playground for the frontend code-block section
- [ ] Mentor Agent gap-detection logic
- [ ] Faculty Copilot drafting logic
- [ ] Moodle fake-data seed script (`moodle_seed/`)
- [ ] Next.js frontend (after backend works)

## Implementation notes
- **Tutor Agent embeddings use Ollama (`nomic-embed-text`), not `sentence-transformers`/HuggingFace.** `requirements.txt` still lists `sentence-transformers`, but it's unused — pulling it installs `torch` (~550MB+ with CUDA deps), and the model weights for any HF-based embedder need a download from huggingface.co or an S3 bucket, both of which can be blocked on restrictive networks. Ollama was already a locked-in local LLM backend, so its embeddings endpoint covers this for free with no extra heavy deps. Run `ollama pull nomic-embed-text` once before using the Tutor Agent. If this turns out to be a problem (e.g. embedding quality), swapping back to `sentence-transformers` just means reimplementing `app/tools/llm_client.embed()`.
- **Gemini calls go through `httpx` directly, not the `google-generativeai` SDK.** That SDK pulls in `google-api-python-client` (16MB+) and a dependency chain built for other Google APIs (Drive, Sheets, OAuth) this project doesn't touch. `_generate_gemini()` in `app/tools/llm_client.py` now POSTs straight to `generativelanguage.googleapis.com`'s REST endpoint — same capability, far lighter. `requirements.txt` updated to drop `google-generativeai`.
- **Code execution runs in a Docker sandbox.** `app/tools/code_runner.py` starts a throwaway container from `backend/sandbox/Dockerfile` (image `agentic-lms-runner`, Python 3 + gcc + Java 17) for every run: no network, read-only filesystem, 512 MB memory, 1 CPU, 128 processes, non-root user, time limit per test. Build it once: `docker build -t agentic-lms-runner backend/sandbox`. `CODE_RUNNER_MODE=local` runs code directly on the machine for development and tests only (not isolated). `code_harness.py` runs inside the sandbox and never sees expected outputs; comparison happens on the host.
- **Code questions are validated before they are served.** The LLM writes the problem, tests and a Python reference solution; the reference is run on the tests, the question is dropped if it crashes or disagrees with more than half of the LLM's expected outputs, and expected outputs are taken from the reference run. The first 2 tests are visible examples, the rest are hidden and redacted in grading results.
- **Fix suggestions are checked.** `app/tools/code_assistant.py` asks the LLM for an explanation plus corrected code, then runs the corrected code; `verified` says whether it actually passes.
- **Tests:** `python -m pytest tests` from `backend/` (offline; LLM and vector store are stubbed; C/Java tests skip if gcc/javac are missing).
- **Quizzes and results are stored (SQLAlchemy).** `app/db/` holds the tables (quizzes, quiz_questions, attempts, attempt_answers). Default is a local SQLite file `backend/agentic_lms.db` (gitignored); set `APP_DB_URL` to any Postgres (Supabase, Neon, Cloud SQL) to switch, no code change. `/assessment/generate` saves the quiz and returns questions **without** answers, explanations, hidden tests or reference solutions (`include_answers=true` is the faculty/testing view). Students submit by question id to `/assessment/quizzes/{quiz_id}/submit`; grading uses the stored answers and the attempt is saved. `/assessment/students/{student_id}/performance` gives accuracy by topic, Bloom level and question type, plus `weak_topics` (< 60%): the Mentor Agent's input. `DATABASE_URL` (old Supabase) is unused.
