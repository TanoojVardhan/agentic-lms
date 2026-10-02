"""ChromaDB vector store — ingestion and retrieval for the Tutor Agent's RAG
pipeline.

Chunking follows the project's chosen spec: recursive character splitting,
512-token target / 64-token overlap (approximated here via characters, see
`_chunk_text` docstring). Embeddings come from `app.tools.llm_client.embed`
(Ollama-backed, local/free) rather than Chroma's bundled default embedder,
which needs to download model weights from a host (huggingface.co /
*.amazonaws.com) that may not be reachable on a locked-down network —
Ollama's own model pull happens once, separately, via `ollama pull`.

One Chroma collection per course_id, so retrieval never crosses course
boundaries.
"""
from __future__ import annotations

from typing import Any, Dict, List

import chromadb
from chromadb.api.models.Collection import Collection

from app.config import settings
from app.tools.llm_client import embed, embed_batch

_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return _client


def _collection_name(course_id: str) -> str:
    # Chroma collection names must be 3-63 chars, alnum/underscore/hyphen.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(course_id))
    return f"course_{safe}"


def _get_collection(course_id: str) -> Collection:
    client = _get_client()
    return client.get_or_create_collection(
        name=_collection_name(course_id),
        metadata={"course_id": str(course_id)},
    )


def _chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> List[str]:
    """Recursive-ish character chunking with overlap.

    `chunk_size`/`overlap` are character counts here, not tokens (avoids an
    extra tokenizer dependency) — 512 tokens of English prose is roughly
    ~1800-2200 characters, but we keep the *settings* field named in tokens
    per the project spec and apply a ~4x multiplier so behavior is in the
    right ballpark without over-claiming token-exactness.
    """
    chunk_size = (chunk_size or settings.rag_chunk_size) * 4
    overlap = (overlap or settings.rag_chunk_overlap) * 4

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    buf = ""
    for para in paragraphs:
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) <= chunk_size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        if len(para) <= chunk_size:
            buf = para
        else:
            # Paragraph itself too long — hard-split with overlap.
            start = 0
            while start < len(para):
                end = start + chunk_size
                chunks.append(para[start:end])
                start = end - overlap
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def ingest_document(course_id: str, text: str, source_name: str) -> int:
    """Chunk + embed + store a document's text under a course's collection.

    Returns the number of chunks ingested.
    """
    chunks = _chunk_text(text)
    if not chunks:
        return 0

    collection = _get_collection(course_id)
    embeddings = embed_batch(chunks)
    ids = [f"{source_name}::{i}" for i in range(len(chunks))]
    metadatas = [{"source": source_name, "chunk_index": i} for i in range(len(chunks))]

    # Overwrite any previous chunks from the same source (re-ingest = replace).
    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return len(chunks)


def query_course_vectorstore(
    query: str, course_id: str, k: int | None = None
) -> List[Dict[str, Any]]:
    """Return the top-k most relevant chunks for a query within one course.

    Each result: {"text": str, "source": str, "chunk_index": int, "distance": float}
    """
    k = k or settings.rag_top_k
    collection = _get_collection(course_id)
    if collection.count() == 0:
        return []

    query_embedding = embed(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, collection.count()),
    )

    out: List[Dict[str, Any]] = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append(
            {
                "text": doc,
                "source": meta.get("source"),
                "chunk_index": meta.get("chunk_index"),
                "distance": dist,
            }
        )
    return out
