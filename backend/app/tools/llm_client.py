"""
Unified LLM client that routes a single `generate()` call to whichever
backend is configured — Ollama (local/free), OpenRouter (free-tier models,
OpenAI-compatible API), or Gemini (free tier). No OpenAI or Anthropic calls
anywhere in this project by design (see capstone decisions).

This lets every agent call one function, and lets evaluation code loop over
all three backends for comparison without touching agent logic.
"""
from __future__ import annotations

from app.config import settings


def generate(prompt: str, backend: str | None = None, system: str | None = None) -> str:
    """Generate a completion from the chosen backend.

    backend: "ollama" | "openrouter" | "gemini" — defaults to settings.default_llm_backend
    """
    backend = backend or settings.default_llm_backend

    if backend == "ollama":
        return _generate_ollama(prompt, system)
    elif backend == "openrouter":
        return _generate_openrouter(prompt, system)
    elif backend == "gemini":
        return _generate_gemini(prompt, system)
    else:
        raise ValueError(f"Unknown LLM backend: {backend!r}")


def _generate_ollama(prompt: str, system: str | None) -> str:
    import ollama

    client = ollama.Client(host=settings.ollama_host)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat(model=settings.ollama_model, messages=messages)
    return response["message"]["content"]


def _generate_openrouter(prompt: str, system: str | None) -> str:
    from openai import OpenAI  # OpenRouter exposes an OpenAI-compatible API

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=settings.openrouter_model,
        messages=messages,
    )
    return response.choices[0].message.content


def _generate_gemini(prompt: str, system: str | None) -> str:
    """Calls Gemini's REST API directly via httpx instead of the
    `google-generativeai` SDK. That SDK pulls in `google-api-python-client`
    (16MB+) and a long dependency chain mostly meant for other Google APIs
    (Drive, Sheets, OAuth flows) that this project doesn't use — a plain
    REST call does the same job with a dependency we already have (httpx).
    """
    import httpx

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    response = httpx.post(
        url,
        params={"key": settings.gemini_api_key},
        json=body,
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response shape: {data}") from exc


def embed(text: str) -> list[float]:
    """Embed a single string of text for vector search.

    Uses Ollama's embedding models (local, free) rather than OpenAI/Anthropic
    embeddings, consistent with this project's LLM-backend decision. Pull a
    model first: `ollama pull nomic-embed-text`.
    """
    import ollama

    client = ollama.Client(host=settings.ollama_host)
    response = client.embeddings(model=settings.ollama_embed_model, prompt=text)
    return response["embedding"]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings. Ollama's embeddings endpoint is single-input,
    so this loops — fine for ingestion-time batch sizes in a capstone project,
    revisit if ingesting large corpora."""
    return [embed(t) for t in texts]
