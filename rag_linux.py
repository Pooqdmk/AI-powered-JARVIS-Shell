

import argparse
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from langchain.schema import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

#data prep

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load a JSONL file into a list of dicts (skip malformed lines)."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[warn] Line {i}: bad JSON ({e}); skipping.")
    return records


def to_text_block(item: Dict[str, Any]) -> str:
    """Convert a Linux command record into a searchable text block."""
    cmd = item.get("command") or item.get("cmd") or item.get("name", "")
    desc = item.get("description") or item.get("desc") or item.get("what", "")
    category = item.get("category") or item.get("topic", "")
    flags = item.get("flags") or item.get("options", [])
    examples = item.get("examples") or item.get("example") or item.get("usage", [])

    def norm(x):
        if isinstance(x, dict):
            return "\n".join(f"{k}: {v}" for k, v in x.items())
        if isinstance(x, (list, tuple)):
            return "\n".join(map(str, x))
        return str(x)

    parts = []
    if cmd:
        parts.append(f"COMMAND: {cmd}")
    if desc:
        parts.append(f"DESCRIPTION: {desc}")
    if category:
        parts.append(f"CATEGORY: {category}")
    if flags:
        txt = norm(flags)
        if txt.strip():
            parts.append("FLAGS/OPTIONS:\n" + txt)
    if examples:
        txt = norm(examples)
        if txt.strip():
            parts.append("EXAMPLES:\n" + txt)

    return "\n".join(parts).strip()


def build_corpus(path: str) -> List[Document]:
    raw = load_jsonl(path)
    docs: List[Document] = []
    for i, rec in enumerate(raw):
        text = to_text_block(rec)
        if not text:
            continue
        metadata = {
            "id": i,
            "command": rec.get("command") or rec.get("cmd") or rec.get("name") or "",
            "category": rec.get("category") or rec.get("topic") or "",
        }
        docs.append(Document(page_content=text, metadata=metadata))
    return docs


#vector store

def get_embeddings(model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    return HuggingFaceEmbeddings(model_name=model_name, show_progress=True)


def build_vectorstore(
    docs: List[Document],
    persist_dir: str,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> FAISS:
    os.makedirs(persist_dir, exist_ok=True)
    embeddings = get_embeddings(model_name)
    vs = FAISS.from_documents(docs, embeddings)
    vs.save_local(persist_dir)
    return vs


def load_vectorstore(
    persist_dir: str,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> FAISS:
    embeddings = get_embeddings(model_name)
    return FAISS.load_local(
        persist_dir, embeddings, allow_dangerous_deserialization=True
    )


#retrival

def retrieve(
    vs: FAISS,
    query: str,
    k: int = 6,
    score_threshold: Optional[float] = None,
    use_mmr: bool = False,
) -> List[Tuple[Document, float]]:
    """Return (doc, score) pairs using similarity or MMR."""
    try:
        if use_mmr:
            docs = vs.max_marginal_relevance_search(query, k=k)
            return [(d, 1.0) for d in docs]
        docs_scores = vs.similarity_search_with_score(query, k=k)
        if score_threshold is not None:
            docs_scores = [p for p in docs_scores if p[1] >= score_threshold]
        return docs_scores
    except Exception as e:
        print(f"[error] Retrieval failed: {e}")
        return []


def format_retrieval_answer(
    question: str, docs: List[Tuple[Document, float]]
) -> str:
    """Pretty-print the retrieved documents."""
    lines = [f"Q: {question}", "", "Top suggestions from the knowledge base:"]
    for i, (d, score) in enumerate(docs, 1):
        cmd = d.metadata.get("command") or "(no command)"
        lines.append(f"\n{i}. {cmd}  [score={score:.3f}]")
        content = d.page_content
        parts = content.split("EXAMPLES:")
        before = parts[0]
        examples = parts[1] if len(parts) > 1 else ""
        desc = next(
            (ln.replace("DESCRIPTION:", "").strip()
             for ln in before.splitlines() if ln.startswith("DESCRIPTION:")),
            ""
        )
        if desc:
            lines.append(f"   - {desc}")
        if examples.strip():
            ex_lines = [l for l in examples.strip().splitlines() if l.strip()][:3]
            if ex_lines:
                lines.append("   Examples:")
                for ex in ex_lines:
                    lines.append(f"     $ {ex.strip()}")
    return "\n".join(lines)


def answer_query(
    vs: FAISS,
    question: str,
    k: int = 6,
    score_threshold: Optional[float] = None,
    use_mmr: bool = False,
) -> str:
    docs_scores = retrieve(vs, question, k=k,
                           score_threshold=score_threshold,
                           use_mmr=use_mmr)
    if not docs_scores:
        return "No relevant results found."
    return format_retrieval_answer(question, docs_scores)


#cli

def cli():
    parser = argparse.ArgumentParser(
        description="Linux Commands Retrieval "
    )
    parser.add_argument("--data", required=True, help="Path to JSONL data file")
    parser.add_argument("--store", default="./vectorstore", help="FAISS store directory")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2",
                        help="Embeddings model")
    parser.add_argument("--ask", type=str, default=None, help="Ask a natural-language question")
    parser.add_argument("-k", type=int, default=6, help="Top-k documents to retrieve")
    parser.add_argument("--score-threshold", type=float, default=None, help="Minimum score for retrieval")
    parser.add_argument("--mmr", action="store_true", help="Use MMR retrieval")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of vector store")
    args = parser.parse_args()

    # Build corpus if vector store missing or rebuild requested
    vs_path = Path(args.store)
    if not vs_path.exists() or args.rebuild:
        print("[*] Building vector store...")
        docs = build_corpus(args.data)
        print(f"[*] Loaded {len(docs)} documents.")
        build_vectorstore(docs, args.store, args.model)
        print(f"[✓] Vector store saved to {args.store}")

    # If a question is asked, perform retrieval
    if args.ask:
        vs = load_vectorstore(args.store, args.model)
        print("[*] Retrieving & answering...")
        out = answer_query(
            vs,
            args.ask,
            k=args.k,
            score_threshold=args.score_threshold,
            use_mmr=args.mmr,
        )
        print("\n" + out + "\n")
    else:
        print("[*] Vector store ready. Use --ask 'your question' to query.")


if __name__ == "__main__":
    cli()
