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
- [ ] ChromaDB ingestion pipeline for Tutor Agent
- [ ] Bloom's-taxonomy quiz generation for Assessment Agent
- [ ] Mentor Agent gap-detection logic
- [ ] Faculty Copilot drafting logic
- [ ] Moodle fake-data seed script (`moodle_seed/`)
- [ ] Next.js frontend (after backend works)
