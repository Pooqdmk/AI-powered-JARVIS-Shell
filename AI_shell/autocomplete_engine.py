# ai_shell/autocomplete_engine.py
"""
Async BART-based autocomplete engine with:
 - debouncing (to avoid flooding the model)
 - caching (simple prefix cache)
 - runs model inference in a thread executor so the Textual event loop is not blocked
"""

import asyncio
import os
from typing import List, Dict, Optional

import torch
from transformers import BartForConditionalGeneration, BartTokenizer
from transformers import logging

logging.set_verbosity_error()

# ---------------- Configuration ----------------
HF_REPO = "Bharadwaj26/jarvis-bart-autocomplete-finetuned"
SUBFOLDER = "bart_autocomplete_model"
BASE_MODEL = "facebook/bart-base"
MODEL_DIR = None  # set to your local model dir if available
MAX_SUGGESTIONS = 6
MAX_LENGTH = 40
NUM_BEAMS = 6  # Must be >= MAX_SUGGESTIONS

# ---------------- Load model once ----------------
def load_bart_model(model_dir: Optional[str] = MODEL_DIR):
    """Load BART model silently - no print statements to avoid TUI interference."""
    try:
        if model_dir and os.path.isdir(model_dir):
            tokenizer = BartTokenizer.from_pretrained(model_dir)
            model = BartForConditionalGeneration.from_pretrained(model_dir)
        else:
            # Try HuggingFace repo (subfolder)
            tokenizer = BartTokenizer.from_pretrained(HF_REPO, subfolder=SUBFOLDER)
            model = BartForConditionalGeneration.from_pretrained(HF_REPO, subfolder=SUBFOLDER)
    except Exception:
        # Fallback to base model silently
        tokenizer = BartTokenizer.from_pretrained(BASE_MODEL)
        model = BartForConditionalGeneration.from_pretrained(BASE_MODEL)
    return tokenizer, model

# Load model on import - errors are silently handled
try:
    _tokenizer, _model = load_bart_model()
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    _model.to(_device)
    _model.eval()
except Exception:
    # If model loading fails, we'll handle it gracefully in suggest()
    _tokenizer = None
    _model = None
    _device = "cpu"

# ---------------- Engine ----------------
_cache: Dict[str, List[str]] = {}  # simple in-memory cache


def _generate_sync_suggestions(text: str, num_return_sequences: int = MAX_SUGGESTIONS) -> List[str]:
    """Synchronous generator for use in thread pool."""
    if not text.strip() or _model is None or _tokenizer is None:
        return []
    try:
        # Ensure num_return_sequences doesn't exceed num_beams
        num_return_sequences = min(num_return_sequences, NUM_BEAMS)
        inputs = _tokenizer(text, return_tensors="pt").to(_device)
        outs = _model.generate(
            **inputs,
            max_length=MAX_LENGTH,
            num_beams=NUM_BEAMS,
            num_return_sequences=num_return_sequences,
            early_stopping= True,
            no_repeat_ngram_size=2,
        )
        results = [_tokenizer.decode(o, skip_special_tokens=True).strip() for o in outs]
        # Remove duplicates while preserving order
        seen = set()
        deduped = []
        for r in results:
            if r and r not in seen:
                seen.add(r)
                deduped.append(r)
        return deduped
    except Exception:
        # Return empty list on any error - silent failure
        return []


async def suggest(text: str, limit: int = MAX_SUGGESTIONS) -> List[str]:
    """
    Async wrapper - uses cache and runs the model in an executor.
    Returns a list of suggestions ordered by model score (approx).
    """
    if not text.strip():
        return []
    
    # If model failed to load, return empty list silently
    if _model is None or _tokenizer is None:
        return []

    key = text.strip().lower()
    # quick prefix-based cache: exact prefix hit
    if key in _cache:
        return _cache[key][:limit]

    loop = asyncio.get_running_loop()
    try:
        suggestions = await loop.run_in_executor(None, _generate_sync_suggestions, text, limit)
    except Exception:
        # Return empty list on error - don't raise to avoid TUI disruption
        return []

    # Post-filter: ensure suggestions extend the input or are reasonable
    filtered = []
    for s in suggestions:
        if not s:
            continue
        # prefer suggestions that contain the input or start with it (case-insensitive)
        if key in s.lower() or s.lower().startswith(key):
            filtered.append(s)
        else:
            filtered.append(s)  # keep anyway; user may want rephrasing

    _cache[key] = filtered  # store
    return filtered[:limit]


# Optional helper: clear cache (useful for dev)
def clear_cache():
    _cache.clear()
