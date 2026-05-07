"""FinBERT sentiment scorer.

We use ProsusAI/finbert — a BERT model fine-tuned on financial news headlines
that emits three logits: positive, negative, neutral. It runs on CPU with
~50 ms latency per headline on a modern x86 box, so batch-scoring a daily
backlog of a few hundred headlines is trivially fast.

Storage convention
------------------
For each stock_news row we store:
  sentiment_label  : "positive" | "negative" | "neutral"
  sentiment_score  : signed magnitude in the range [-1, 1]
                     (positive_prob - negative_prob)
                     so a strong positive sits near +1, strong negative near -1,
                     neutral near 0. This is more useful than per-class probs
                     because it composes nicely (averages, sums) when you want
                     to compute a per-stock 14-day rolling sentiment in the
                     scoring engine later.

The model is downloaded once on first start (about 440 MB) and cached at
/root/.cache/huggingface inside the container — bind that to a volume in
docker-compose.yml if you want it to persist across rebuilds.
"""
from __future__ import annotations

import os
import threading
from typing import Iterable

import structlog


_MODEL_ID = os.environ.get("SENTIMENT_MODEL", "ProsusAI/finbert")
_BATCH_SIZE = int(os.environ.get("SENTIMENT_BATCH_SIZE", "16"))
_log = structlog.get_logger("sentiment")

# Lazily loaded so worker threads don't all duplicate the load.
_model = None
_tokenizer = None
_id2label: dict[int, str] = {}
_lock = threading.Lock()


def _ensure_loaded():
    global _model, _tokenizer, _id2label
    if _model is not None:
        return
    with _lock:
        if _model is not None:
            return
        # Local import — keeps the module importable even before deps install.
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch  # noqa: F401  (forces eager import for clearer error)
        _log.info("sentiment_model_loading", model=_MODEL_ID)
        _tokenizer = AutoTokenizer.from_pretrained(_MODEL_ID)
        _model = AutoModelForSequenceClassification.from_pretrained(_MODEL_ID)
        _model.eval()
        _id2label = {int(k): v.lower() for k, v in _model.config.id2label.items()}
        _log.info("sentiment_model_loaded", labels=list(_id2label.values()))


def score_text(text: str) -> tuple[str, float]:
    """Single-headline scoring. Returns (label, signed_score)."""
    return score_batch([text])[0]


def score_batch(texts: Iterable[str]) -> list[tuple[str, float]]:
    """Batched scoring. Returns one (label, signed_score) per input string.

    Inputs longer than the tokenizer's max length are silently truncated. None
    or empty strings get a default ('neutral', 0.0) so they don't break the
    batch.
    """
    _ensure_loaded()
    import torch

    cleaned: list[str] = []
    placeholder_idx: list[int] = []
    for i, t in enumerate(texts):
        if not t or not t.strip():
            placeholder_idx.append(i)
            cleaned.append("")
        else:
            cleaned.append(t.strip())

    out: list[tuple[str, float]] = [("neutral", 0.0)] * len(cleaned)
    real_indices = [i for i in range(len(cleaned)) if i not in set(placeholder_idx)]
    if not real_indices:
        return out

    real_texts = [cleaned[i] for i in real_indices]
    with torch.inference_mode():
        for chunk_start in range(0, len(real_texts), _BATCH_SIZE):
            chunk = real_texts[chunk_start:chunk_start + _BATCH_SIZE]
            chunk_idx = real_indices[chunk_start:chunk_start + _BATCH_SIZE]
            inputs = _tokenizer(
                chunk, padding=True, truncation=True, max_length=128, return_tensors="pt",
            )
            logits = _model(**inputs).logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
            for row_idx, ps in zip(chunk_idx, probs):
                # Map by label name so we don't depend on a particular ordering
                # of the three logits (FinBERT canonical order is positive/
                # negative/neutral but newer mirrors sometimes differ).
                label_probs = {_id2label[i]: float(p) for i, p in enumerate(ps)}
                pos = label_probs.get("positive", 0.0)
                neg = label_probs.get("negative", 0.0)
                neu = label_probs.get("neutral", 0.0)
                # winning label
                label = max(label_probs, key=label_probs.get)
                signed = pos - neg
                out[row_idx] = (label, round(signed, 4))
    return out
