from rag_engine import ensure_vectorstore

print("[*] Rebuilding vectorstore...")
ensure_vectorstore(rebuild=True)
print("[✓] Vectorstore rebuilt successfully!")
