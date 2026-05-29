"""Local MiniLM-based embedding generation.

Uses ``sentence-transformers`` with the ``all-MiniLM-L6-v2`` model. Produces
384-dimensional float vectors. Model downloads (~80 MB) on first call and is
cached locally by Hugging Face's default cache, then loaded once per process
and reused.

Why local and not OpenAI:
- Free, no API key required.
- Runs offline / works in airgapped dev.
- No rate limits.
- 384 dims matches our existing ``embeddings.embedding`` column (vector(384)).

Cost: ~50-100 ms per embed on CPU. Acceptable for sync calls during admin
CRUD (the admin already accepts that kind of latency).

Public surface:
- ``embed_text(text: str) -> list[float]`` — returns a 384-dim vector
- ``EMBEDDING_DIM`` — the vector dimension (384)
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


# Module-level cache for the loaded model. Loaded lazily on first call to
# embed_text so application startup stays fast. A simple lock guards against
# two concurrent requests both trying to load the model on first hit.
_model: "SentenceTransformer | None" = None
_model_lock = threading.Lock()


def _get_model() -> "SentenceTransformer":
    """Return the singleton SentenceTransformer model.

    Imports ``sentence_transformers`` lazily so that merely importing this
    module does not pay the ~1-2 s import cost. The model itself loads (and
    downloads, on first run) inside the lock.
    """
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is None:  # double-checked locking
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", MODEL_NAME)
            _model = SentenceTransformer(MODEL_NAME)
            logger.info("Embedding model loaded; dim=%s", EMBEDDING_DIM)
    return _model


def embed_text(text: str) -> list[float]:
    """Encode a single text string into a 384-dim float vector.

    Empty strings are tolerated: the model produces a deterministic embedding
    for empty input, which is fine for our use case (the row will exist but
    won't match anything semantically meaningful).

    Args:
        text: The text to embed. Should already be assembled by the caller
              (e.g. "Root Canal. A standard endodontic procedure.") — this
              helper does not do any string composition.

    Returns:
        A 384-element list of floats. Suitable for direct insert into the
        ``embeddings.embedding`` pgvector column.
    """
    model = _get_model()
    vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    # .tolist() converts numpy float32 to native Python floats; pgvector
    # accepts either, but list[float] is what our SQLAlchemy column type
    # declares.
    return vector.tolist()
