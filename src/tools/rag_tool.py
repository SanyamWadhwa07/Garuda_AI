"""RAG (Retrieval-Augmented Generation) tool for GarudaAI.

Chunks documents, embeds them via Ollama, stores in ChromaDB, and retrieves
relevant context for user queries. Requires: pip install garudaai[rag]
"""

from __future__ import annotations

from pathlib import Path
from typing import List

_DATA_DIR = Path("~/.local/share/garudaai").expanduser()
_OLLAMA_URL = "http://localhost:11434"
_EMBED_MODEL = "nomic-embed-text"
_CHUNK_SIZE = 512   # words
_CHUNK_OVERLAP = 64  # words


class RAGTool:
    """Embed, store, and retrieve documents using ChromaDB + Ollama embeddings."""

    def __init__(self, ollama_url: str = _OLLAMA_URL):
        import chromadb
        self._ollama_url = ollama_url
        db_path = str(_DATA_DIR / "rag")
        self._client = chromadb.PersistentClient(path=db_path)
        self._col = self._client.get_or_create_collection(
            "documents",
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(self, file_path: Path) -> str:
        """Chunk, embed, and upsert a file. Returns a status string."""
        text = self._extract_text(file_path)
        if not text.strip():
            return f"No text extracted from {file_path.name}"
        chunks = self._chunk(text)
        if not chunks:
            return f"No chunks generated from {file_path.name}"
        embeddings = [self._embed(c) for c in chunks]
        ids = [f"{file_path.name}::{i}" for i in range(len(chunks))]
        self._col.upsert(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=[{"source": file_path.name}] * len(chunks),
        )
        return f"Ingested {len(chunks)} chunks from {file_path.name}"

    def query(self, question: str, n: int = 5) -> str:
        """Return top-N relevant chunks for a question as formatted text."""
        if self._col.count() == 0:
            return "No documents ingested yet. Upload files in Settings → Documents."
        emb = self._embed(question)
        results = self._col.query(query_embeddings=[emb], n_results=min(n, self._col.count()))
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        parts = []
        for doc, meta in zip(docs, metas):
            src = meta.get("source", "unknown")
            parts.append(f"[{src}]\n{doc}")
        return "\n\n".join(parts)

    def list_sources(self) -> List[str]:
        """Return sorted list of unique source file names."""
        if self._col.count() == 0:
            return []
        result = self._col.get(include=["metadatas"])
        seen: set = set()
        sources = []
        for meta in result.get("metadatas", []):
            src = meta.get("source", "")
            if src and src not in seen:
                seen.add(src)
                sources.append(src)
        return sorted(sources)

    def delete_source(self, source_name: str) -> str:
        """Remove all chunks from a given source."""
        result = self._col.get(where={"source": source_name}, include=["documents"])
        ids = result.get("ids", [])
        if not ids:
            return f"Source '{source_name}' not found"
        self._col.delete(ids=ids)
        return f"Deleted {len(ids)} chunks from '{source_name}'"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _extract_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                return " ".join(
                    (page.extract_text() or "") for page in reader.pages
                )
            except ImportError:
                raise RuntimeError("pypdf not installed. Run: pip install garudaai[rag]")
        # Plain text / markdown / code files
        return path.read_text(encoding="utf-8", errors="ignore")

    def _chunk(self, text: str) -> List[str]:
        words = text.split()
        chunks = []
        step = _CHUNK_SIZE - _CHUNK_OVERLAP
        for i in range(0, len(words), step):
            chunk = " ".join(words[i : i + _CHUNK_SIZE])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    def _embed(self, text: str) -> List[float]:
        import httpx
        try:
            r = httpx.post(
                f"{self._ollama_url}/api/embeddings",
                json={"model": _EMBED_MODEL, "prompt": text},
                timeout=30.0,
            )
            r.raise_for_status()
            return r.json()["embedding"]
        except Exception as e:
            raise RuntimeError(f"Embedding failed (is Ollama running with {_EMBED_MODEL}?): {e}")
