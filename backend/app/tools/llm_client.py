"""
Unified LLM client that routes a single `generate()` call to whichever
backend is configured — Ollama (local/free), OpenRouter (free-tier models,
OpenAI-compatible API), or Gemini (free tier). No OpenAI or Anthropic calls
anywhere in this project by design (see capstone decisions).

This lets every agent call one function, and lets evaluation code loop over
all three backends for comparison without touching agent logic.

Every failure is raised as `LLMError` with a readable message, so API routes
can return a clean 503 instead of a 500 traceback.
"""
from __future__ import annotations

import time
from functools import lru_cache

import httpx

from app.config import settings

# Gemini free tier hits 429 (rate limit) and occasional 503s; retry those.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 2  # so up to 3 attempts, waiting 2s then 4s


class LLMError(RuntimeError):
    """An LLM backend call failed (unreachable, misconfigured or bad reply)."""


def generate(prompt: str, backend: str | None = None, system: str | None = None) -> str:
    """Generate a completion from the chosen backend.

    backend: "ollama" | "openrouter" | "gemini" — defaults to settings.default_llm_backend
    """
    backend = (backend or settings.default_llm_backend).lower()
    handlers = {
        "ollama": _generate_ollama,
        "openrouter": _generate_openrouter,
        "gemini": _generate_gemini,
    }
    if backend not in handlers:
        raise LLMError(f"Unknown LLM backend {backend!r}; use ollama, openrouter or gemini.")
    try:
        return handlers[backend](prompt, system)
    except LLMError:
        raise
    except Exception as exc:  # network errors, missing models, SDK errors
        raise LLMError(f"{backend} call failed: {exc}") from exc


def _messages(prompt: str, system: str | None) -> list[dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


@lru_cache(maxsize=1)
def _ollama_client():
    import ollama

    return ollama.Client(host=settings.ollama_host)


@lru_cache(maxsize=1)
def _openrouter_client():
    from openai import OpenAI  # OpenRouter exposes an OpenAI-compatible API

    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        max_retries=MAX_RETRIES,
    )


def _generate_ollama(prompt: str, system: str | None) -> str:
    response = _ollama_client().chat(
        model=settings.ollama_model, messages=_messages(prompt, system)
    )
    return response["message"]["content"]


def _generate_openrouter(prompt: str, system: str | None) -> str:
    if not settings.openrouter_api_key or not settings.openrouter_model or \
            "replace" in settings.openrouter_api_key:
        raise LLMError("OpenRouter is not configured: set OPENROUTER_API_KEY and OPENROUTER_MODEL in backend/.env.")
    response = _openrouter_client().chat.completions.create(
        model=settings.openrouter_model,
        messages=_messages(prompt, system),
    )
    return response.choices[0].message.content


def _generate_gemini(prompt: str, system: str | None) -> str:
    """Calls Gemini's REST API directly via httpx instead of the
    `google-generativeai` SDK. That SDK pulls in `google-api-python-client`
    (16MB+) and a long dependency chain mostly meant for other Google APIs
    (Drive, Sheets, OAuth flows) that this project doesn't use — a plain
    REST call does the same job with a dependency we already have (httpx).

    The key goes in the x-goog-api-key header rather than the URL, so it
    never shows up in logged request URLs.
    """
    if not settings.gemini_api_key or "replace" in settings.gemini_api_key:
        raise LLMError("Gemini is not configured: set GEMINI_API_KEY in backend/.env.")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    response = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = httpx.post(
                url,
                headers={"x-goog-api-key": settings.gemini_api_key},
                json=body,
                timeout=60.0,
            )
        except httpx.TransportError as exc:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt + 1))
                continue
            raise LLMError(f"Could not reach Gemini: {exc}") from exc
        if response.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
            time.sleep(2 ** (attempt + 1))
            continue
        break

    if response.status_code >= 400:
        hint = " (free-tier rate limit; wait a minute)" if response.status_code == 429 else ""
        raise LLMError(f"Gemini returned HTTP {response.status_code}{hint}: {response.text[:300]}")

    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        feedback = data.get("promptFeedback") if isinstance(data, dict) else None
        raise LLMError(f"Gemini returned no answer (feedback: {feedback})") from exc


def embed(text: str) -> list[float]:
    """Embed a single string of text for vector search.

    Uses Ollama's embedding models (local, free) rather than OpenAI/Anthropic
    embeddings, consistent with this project's LLM-backend decision. Pull a
    model first: `ollama pull nomic-embed-text`.

    Deliberately stays on the legacy `embeddings` endpoint: the newer batch
    `embed` endpoint returns normalized vectors, which would not match the
    457 chunks already stored in ChromaDB. Switching needs a full re-ingest.
    """
    try:
        response = _ollama_client().embeddings(model=settings.ollama_embed_model, prompt=text)
    except Exception as exc:
        raise LLMError(
            f"Ollama embedding failed ({exc}). Is Ollama running and is "
            f"{settings.ollama_embed_model!r} pulled?"
        ) from exc
    return response["embedding"]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings, one request each (see `embed` for why)."""
    return [embed(t) for t in texts]
