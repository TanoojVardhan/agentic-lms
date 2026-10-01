# Agentic LMS

> A Quad-Agent Collaborative AI Framework for Personalized Education and Faculty Support (tentative title)

Four collaborating AI agents integrated into Moodle via REST APIs:
- **Tutor Agent** — syllabus-grounded Q&A via RAG (ChromaDB)
- **Assessment Agent** — Bloom's-taxonomy quiz generation + grading
- **Learning Path & Mentor Agent** — knowledge-gap detection from Moodle interaction logs
- **Faculty Copilot Agent** — lecture drafting, question banks, cohort analytics

Full technical spec: see the project doc `gemini-code-1790865916533.md` (one level up). Ideation/decision notes: `capstone-ideation-notes.md` in the CAPSTONE project.

## Stack
- Backend: Python 3.10+, FastAPI, LangGraph
- RAG: ChromaDB
- DB: Postgres (shared, cloud-hosted — see `.env`)
- LMS: Moodle (local Docker instance, per-person — see `docker-compose.yml`)
- LLMs: Ollama (local/free), OpenRouter (free-tier), Gemini (free tier) — **no OpenAI or Anthropic API usage**
- Frontend: Next.js (built after backend is working)

## Getting started
```bash
cd backend
pip install -r ../requirements.txt   # installed directly, no virtualenv
cp ../.env.example ../.env   # fill in your keys
uvicorn app.main:app --reload
```

Moodle (separate terminal, requires Docker):
```bash
docker compose up -d
# then visit http://localhost:8080, enable Web Services + REST protocol,
# generate a service token, and put it in .env as MOODLE_WS_TOKEN
```

## Status
Scaffold stage — FastAPI app, LangGraph state/graph wiring, Moodle REST client, and 4 agent stubs are in place. Agent logic (RAG retrieval, quiz generation, gap detection, lecture drafting) not yet implemented.
