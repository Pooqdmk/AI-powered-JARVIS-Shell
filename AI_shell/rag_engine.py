"""
RAG engine for JARVIS Shell.

- Loads Linux + PowerShell command datasets from AI_shell/datasets/
- Builds a FAISS vectorstore in AI_shell/vectorstore/
- Uses HuggingFace sentence-transformer embeddings
- Provides simple APIs for the rest of the app:
    - ensure_vectorstore(rebuild=False)
    - rag_answer(question: str, k: int = 6) -> str
    - rag_suggestions(question: str, k: int = 6) -> list[dict]

Linux commands are ranked before PowerShell commands in the final answer.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# ---------------- Paths & config ----------------

BASE_DIR = Path(__file__).parent
DATASET_DIR = BASE_DIR / "datasets"
VECTORSTORE_DIR = BASE_DIR / "vectorstore"

DEFAULT_DATASETS = [
    DATASET_DIR / "LINUX_TERMINAL_COMMANDS.jsonl",
    DATASET_DIR / "POWERSHELL_COMMANDS.jsonl",
]

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Global singleton vectorstore
_VS: Optional[FAISS] = None


# ---------------- Utilities ----------------

def _load_jsonl(path: Path) -> List[Dict]:
    records: List[Dict] = []
    if not path.exists():
        print(f"[RAG] WARNING: dataset not found: {path}")
        return records

    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except json.JSONDecodeError as e:
                print(f"[RAG] WARNING: bad JSON in {path.name} line {line_num}: {e}; skipping.")
    return records


def _record_to_text_block(rec: Dict) -> str:
    """Convert a JSONL record into a single text block for embedding."""
    parts = []

    cmd = rec.get("command") or rec.get("cmd") or rec.get("name")
    if cmd:
        parts.append(f"COMMAND: {cmd}")

    desc = rec.get("description") or rec.get("desc")
    if desc:
        parts.append(f"DESCRIPTION: {desc}")

    usage = rec.get("usage") or rec.get("syntax")
    if usage:
        parts.append(f"USAGE: {usage}")

    example = rec.get("example") or rec.get("examples")
    if example:
        parts.append(f"EXAMPLE: {example}")

    # If nothing, fall back to raw
    if not parts:
        return json.dumps(rec, ensure_ascii=False)

    return "\n".join(parts)


def _build_documents(dataset_paths: List[Path]) -> List[Document]:
    docs: List[Document] = []

    for path in dataset_paths:
        print(f"[RAG] Loading dataset: {path.name}")
        records = _load_jsonl(path)
        for rec in records:
            text = _record_to_text_block(rec)
            if not text.strip():
                continue

            metadata = {
                "source_file": path.name,
                "command": rec.get("command") or rec.get("cmd") or rec.get("name") or "",
                "category": rec.get("category") or rec.get("topic") or "",
            }
            docs.append(Document(page_content=text, metadata=metadata))

    print(f"[RAG] Total documents loaded: {len(docs)}")
    return docs


def _get_embeddings():
    # Same behavior as your previous rag_linux.py
    print(f"[RAG] Loading embeddings model: {EMBEDDING_MODEL_NAME}")
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME, show_progress=True)


def _build_vectorstore(docs: List[Document]) -> FAISS:
    embeddings = _get_embeddings()
    print("[RAG] Building FAISS vectorstore...")
    vs = FAISS.from_documents(docs, embeddings)

    # Ensure vectorstore directory exists
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    vs.save_local(str(VECTORSTORE_DIR))
    print(f"[RAG] Vectorstore saved to {VECTORSTORE_DIR}")
    return vs


def _load_vectorstore() -> FAISS:
    embeddings = _get_embeddings()
    print(f"[RAG] Loading FAISS vectorstore from {VECTORSTORE_DIR}...")
    vs = FAISS.load_local(
        str(VECTORSTORE_DIR),
        embeddings,
        allow_dangerous_deserialization=True,
    )
    print("[RAG] Vectorstore loaded.")
    return vs


# ---------------- Public API ----------------

def ensure_vectorstore(rebuild: bool = False) -> Optional[FAISS]:
    """
    Ensure the global vectorstore is loaded.
    If `rebuild=True` or vectorstore folder is missing, rebuild from datasets.
    """
    global _VS

    if rebuild or not VECTORSTORE_DIR.exists():
        print("[RAG] Rebuilding vectorstore from datasets...")
        docs = _build_documents(DEFAULT_DATASETS)
        if not docs:
            print("[RAG] ERROR: No documents loaded; cannot build vectorstore.")
            _VS = None
            return None
        _VS = _build_vectorstore(docs)
        return _VS

    if _VS is None:
        try:
            _VS = _load_vectorstore()
        except Exception as e:
            print(f"[RAG] ERROR loading vectorstore: {e}")
            _VS = None
    return _VS


def _score_source_priority(source_file: str) -> int:
    """
    Lower score = higher priority in sorting.
    - Linux datasets first
    - PowerShell second
    - Others last
    """
    name = source_file.lower()
    if "linux" in name:
        return 0
    if "powershell" in name or "ps" in name:
        return 1
    return 2


def rag_suggestions(question: str, k: int = 6) -> List[Dict]:
    """
    Return a list of suggestion dicts for a question.
    Each suggestion dict contains: text, source_file, command, score
    """
    vs = ensure_vectorstore(rebuild=False)
    if vs is None:
        return []

    if not question.strip():
        return []

    # Using similarity search with scores
    docs_and_scores: List[Tuple[Document, float]] = vs.similarity_search_with_score(question, k=k * 2)

    results: List[Dict] = []
    for doc, score in docs_and_scores:
        src = doc.metadata.get("source_file", "")
        cmd = doc.metadata.get("command", "")
        results.append(
            {
                "text": doc.page_content,
                "source_file": src,
                "command": cmd,
                "score": float(score),
            }
        )

    # Sort: by source priority first (Linux > PowerShell > others), then by score
    results.sort(key=lambda r: (_score_source_priority(r["source_file"]), r["score"]))

    return results[:k]


def rag_answer(question: str, k: int = 6):
    """
    Return a structured RAG response compatible with the TUI.
    Smart OS filtering + explicit keyword filtering.
    """

    import platform
    os_name = platform.system().lower()   # "windows", "linux", "darwin"

    q_lower = question.lower()
    suggestions = rag_suggestions(question, k=k)

    if not suggestions:
        return {
            "rag": True,
            "answer": f"No relevant commands found for: {question}",
            "references": [],
            "suggestions": []
        }

    # ------------------------------------------------------------------
    # Split by source file
    # ------------------------------------------------------------------
    linux_cmds = [s for s in suggestions if "linux" in s["source_file"].lower()]
    ps_cmds    = [s for s in suggestions if "powershell" in s["source_file"].lower()]

    # ------------------------------------------------------------------
    # Priority 1: User explicitly requests PowerShell
    # ------------------------------------------------------------------
    if "powershell" in q_lower or "ps " in q_lower or "windows" in q_lower:
        filtered = ps_cmds if ps_cmds else suggestions   # fallback if empty

    # ------------------------------------------------------------------
    # Priority 2: User explicitly requests Linux
    # ------------------------------------------------------------------
    elif "linux" in q_lower or "ubuntu" in q_lower or "centos" in q_lower:
        filtered = linux_cmds if linux_cmds else suggestions

    # ------------------------------------------------------------------
    # Priority 3: Auto OS Matching
    # ------------------------------------------------------------------
    else:
        if os_name == "windows":           # Windows machine
            filtered = ps_cmds if ps_cmds else suggestions
        else:                               # Linux/macOS machine
            filtered = linux_cmds if linux_cmds else suggestions

    # ------------------------------------------------------------------
    # Build the response
    # ------------------------------------------------------------------
    refs = list({s["source_file"] for s in filtered})

    summary = f"Based on your question: '{question}', here are relevant commands."

    return {
        "rag": True,
        "answer": summary,
        "references": refs,
        "suggestions": filtered
    }





# ---------------- CLI (optional, for testing) ----------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG engine test (Linux + PowerShell)")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild vectorstore from datasets")
    parser.add_argument("--ask", type=str, help="Ask a question against the vectorstore", default=None)
    args = parser.parse_args()

    if args.rebuild:
        ensure_vectorstore(rebuild=True)
    else:
        ensure_vectorstore(rebuild=False)

    if args.ask:
        print()
        print(rag_answer(args.ask))
