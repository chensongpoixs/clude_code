from __future__ import annotations

from typing import List, Optional

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None  # type: ignore

class CodeEmbedder:
    """
    Wrapper around fastembed for generating vector embeddings locally.
    Default model: bge-small-en-v1.5 (384 dimensions).
    """
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model: Optional[TextEmbedding] = None

    def _load_model(self):
        if TextEmbedding is None:
            raise RuntimeError("fastembed is not installed. Please run `pip install fastembed`.")
        if self._model is None:
            # This will download the model on first run
            self._model = TextEmbedding(model_name=self.model_name)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of strings.
        """
        self._load_model()
        if self._model is None:
            return []
        
        # fastembed returns a generator of numpy arrays
        embeddings = list(self._model.embed(texts))
        return [e.tolist() for e in embeddings]

    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query string.
        """
        return self.embed_texts([query])[0]

