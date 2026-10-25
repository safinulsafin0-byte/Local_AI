"""
JARVIS Local ONNX Embedding Engine (models/all-MiniLM-L6-v2)
===========================================================
High-performance, pure offline, 384-dimensional text embeddings
using the bundled all-MiniLM-L6-v2 ONNX model and tokenizers library.
Eliminates heavy/broken C-extensions, works reliably on Python 3.14.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Union
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models" / "all-MiniLM-L6-v2"
ONNX_PATH = MODEL_DIR / "onnx" / "model.onnx"
TOKENIZER_PATH = MODEL_DIR / "tokenizer.json"


class LocalMiniLMEmbedder:
    """Drop-in high speed replacement for SentenceTransformer('all-MiniLM-L6-v2')."""

    def __init__(self, model_path: str | Path = ONNX_PATH, tokenizer_path: str | Path = TOKENIZER_PATH):
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_padding(length=128)
        self.tokenizer.enable_truncation(max_length=128)
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress_bar: bool = False,
        **kwargs,
    ) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            encodings = self.tokenizer.encode_batch(batch)

            input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
            token_type_ids = np.array([e.type_ids for e in encodings], dtype=np.int64)

            inputs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            }
            outputs = self.session.run(None, inputs)

            token_embeddings = outputs[0]
            mask = np.expand_dims(attention_mask, -1).astype(np.float32)
            sum_embeddings = np.sum(token_embeddings * mask, axis=1)
            sum_mask = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
            batch_emb = sum_embeddings / sum_mask

            norms = np.linalg.norm(batch_emb, axis=1, keepdims=True)
            batch_emb = batch_emb / np.clip(norms, a_min=1e-9, a_max=None)
            all_embeddings.append(batch_emb)

        return np.vstack(all_embeddings)


_default_embedder = None


def get_embedder() -> LocalMiniLMEmbedder:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = LocalMiniLMEmbedder()
    return _default_embedder

