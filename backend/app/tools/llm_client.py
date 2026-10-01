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
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        settings.gemini_model,
        system_instruction=system,
    )
    response = model.generate_content(prompt)
    return response.text
