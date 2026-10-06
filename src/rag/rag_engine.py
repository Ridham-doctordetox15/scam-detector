"""RAG retrieval over the scam-pattern knowledge base.

Embeds each knowledge-base entry with a multilingual sentence-embedding model,
persists the vectors in a local ChromaDB store, and retrieves the top-k
closest entries (with a cosine similarity score) for an arbitrary message.
The index is rebuilt automatically whenever the knowledge-base JSON (or the
chosen embedding text/model) changes, via a content hash - never on a stale
copy.

Two "what to embed" variants are supported (see :data:`TEXT_VARIANT_PHRASES`
and :data:`TEXT_VARIANT_PHRASES_HOW`); :mod:`src.rag.evaluate` compares them
on the evaluation set and records which one this project uses.

Usage::

    python -m src.rag.rag_engine
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from src.rag.schema import DEFAULT_KB_PATH, load_knowledge_base

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_PERSIST_DIR = Path("chroma_db")

TEXT_VARIANT_PHRASES = "phrases"            # name + typical_phrases
TEXT_VARIANT_PHRASES_HOW = "phrases_how"     # name + typical_phrases + how_it_works
TEXT_VARIANTS = (TEXT_VARIANT_PHRASES, TEXT_VARIANT_PHRASES_HOW)

# Chosen after comparing both variants on the evaluation set (see results.md,
# Phase 6 section, and src/rag/evaluate.py). Overridable per RAGEngine instance.
DEFAULT_TEXT_VARIANT = TEXT_VARIANT_PHRASES_HOW

# Minimum cosine similarity for a top-1 match to be treated as confident,
# chosen from the evaluation set (see results.md, Phase 6: swept to balance
# "matched rows stay confident" against "no_match rows correctly decline",
# based on only 3 no_match examples - a coarse estimate, not a tuned one).
# Below this, retrieve() reports no confident match so Phase 7 never forces
# a pattern onto an unrelated message.
DEFAULT_MIN_CONFIDENT_SIMILARITY = 0.49

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


def compose_document(entry: dict, text_variant: str = DEFAULT_TEXT_VARIANT) -> str:
    """The text embedded for one knowledge-base entry, per ``text_variant``."""
    if text_variant not in TEXT_VARIANTS:
        raise ValueError(f"unknown text_variant {text_variant!r}, expected one of {TEXT_VARIANTS}")
    parts = [entry["name"], *entry["typical_phrases"]]
    if text_variant == TEXT_VARIANT_PHRASES_HOW:
        parts.append(entry["how_it_works"])
    return "\n".join(parts)


def _content_hash(entries: list[dict], text_variant: str, model_name: str) -> str:
    """Stable hash of everything that determines the index's contents."""
    canonical = json.dumps(
        {"entries": entries, "text_variant": text_variant, "model_name": model_name},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _default_embed_fn(model_name: str) -> EmbedFn:
    """Lazily load a real SentenceTransformer model (heavy import, needs internet on first use)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def embed(texts: Sequence[str]) -> list[list[float]]:
        return model.encode(list(texts), normalize_embeddings=True).tolist()

    return embed


@dataclass
class RetrievalMatch:
    """One retrieved knowledge-base entry."""

    entry_id: str
    name: str
    category: str
    similarity: float


@dataclass
class RetrievalResult:
    """The outcome of one :meth:`RAGEngine.retrieve` call."""

    query: str
    matches: list[RetrievalMatch]
    confident: bool  # True iff matches and matches[0].similarity >= the engine's threshold


class RAGEngine:
    """Embeds and retrieves scam-pattern knowledge-base entries via ChromaDB."""

    def __init__(
        self,
        kb_path: Path | str = DEFAULT_KB_PATH,
        persist_dir: Path | str = DEFAULT_PERSIST_DIR,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        text_variant: str = DEFAULT_TEXT_VARIANT,
        collection_name: str | None = None,
        embed_fn: EmbedFn | None = None,
        min_confident_similarity: float = DEFAULT_MIN_CONFIDENT_SIMILARITY,
    ) -> None:
        if text_variant not in TEXT_VARIANTS:
            raise ValueError(f"unknown text_variant {text_variant!r}, expected one of {TEXT_VARIANTS}")
        self.kb_path = Path(kb_path)
        self.persist_dir = Path(persist_dir)
        self.model_name = model_name
        self.text_variant = text_variant
        self.collection_name = collection_name or f"scam_patterns_{text_variant}"
        self.min_confident_similarity = min_confident_similarity
        self._embed_fn = embed_fn  # None => lazily built from model_name on first use
        self._client = None
        self._collection = None

    def _get_embed_fn(self) -> EmbedFn:
        if self._embed_fn is None:
            self._embed_fn = _default_embed_fn(self.model_name)
        return self._embed_fn

    def _get_client(self):
        if self._client is None:
            import chromadb

            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        return self._client

    def _hash_path(self) -> Path:
        return self.persist_dir / f"{self.collection_name}.hash"

    def build_index(self, force: bool = False) -> int:
        """(Re)build the index if the knowledge base/variant/model changed since last build.

        Returns:
            The number of entries in the index after this call (0 for an empty
            knowledge base - not an error).
        """
        entries = load_knowledge_base(self.kb_path)
        current_hash = _content_hash(entries, self.text_variant, self.model_name)
        hash_path = self._hash_path()
        stale = force or not hash_path.exists() or hash_path.read_text(encoding="utf-8").strip() != current_hash

        client = self._get_client()
        if stale:
            try:
                client.delete_collection(self.collection_name)
            except Exception:  # noqa: BLE001 - collection may not exist yet
                pass
            self._collection = client.get_or_create_collection(
                self.collection_name, metadata={"hnsw:space": "cosine"}
            )
            if entries:
                documents = [compose_document(e, self.text_variant) for e in entries]
                embeddings = self._get_embed_fn()(documents)
                self._collection.upsert(
                    ids=[e["id"] for e in entries],
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=[{"name": e["name"], "category": e["category"]} for e in entries],
                )
            hash_path.write_text(current_hash, encoding="utf-8")
            logger.info("Rebuilt index %s: %d entries", self.collection_name, len(entries))
        else:
            self._collection = client.get_or_create_collection(
                self.collection_name, metadata={"hnsw:space": "cosine"}
            )
        return self._collection.count()

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        """Return the top-``k`` closest knowledge-base entries to ``query``.

        Never raises on an empty knowledge base or a query unrelated to every
        entry - it returns whatever matches exist (possibly none) and marks
        ``confident`` accordingly.
        """
        if self._collection is None:
            self.build_index()
        assert self._collection is not None
        if self._collection.count() == 0:
            return RetrievalResult(query=query, matches=[], confident=False)

        n_results = min(top_k, self._collection.count())
        [query_embedding] = self._get_embed_fn()([query])
        result = self._collection.query(query_embeddings=[query_embedding], n_results=n_results)
        matches = [
            RetrievalMatch(entry_id=entry_id, name=meta["name"], category=meta["category"], similarity=1.0 - distance)
            for entry_id, meta, distance in zip(result["ids"][0], result["metadatas"][0], result["distances"][0])
        ]
        confident = bool(matches) and matches[0].similarity >= self.min_confident_similarity
        return RetrievalResult(query=query, matches=matches, confident=confident)


def _print_demo() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = RAGEngine()
    engine.build_index()
    demo_queries = [
        "your kyc will expire today, click here to update or your account will be blocked",
        "your otp for login is 384921, do not share this with anyone",
        "flat 40% off on your favourite brand this weekend only, shop now",
        "the weather is nice today, want to grab coffee later?",
    ]
    for query in demo_queries:
        result = engine.retrieve(query, top_k=3)
        print(f"\nQuery: {query}")
        print(f"  confident: {result.confident}")
        for m in result.matches:
            print(f"  - {m.entry_id} ({m.category}) similarity={m.similarity:.3f}")


if __name__ == "__main__":
    _print_demo()
