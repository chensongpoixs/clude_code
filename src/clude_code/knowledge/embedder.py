from __future__ import annotations

import logging
from typing import List, Optional

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None  # type: ignore

from clude_code.config import CludeConfig

class CodeEmbedder:
    """
    Wrapper around fastembed for generating vector embeddings locally.
    Default model: BAAI/bge-small-zh-v1.5 (384 dimensions).
    """
    def __init__(self, cfg: Optional[CludeConfig] = None):
        self._logger = logging.getLogger(__name__)
        self._device = "cpu"
        if cfg:
            self.model_name = cfg.rag.embedding_model
            self.cache_dir = cfg.rag.model_cache_dir
            self._device = (cfg.rag.device or "cpu").lower()
        else:
            self.model_name = "BAAI/bge-small-zh-v1.5"
            self.cache_dir = None
        self._model: Optional[TextEmbedding] = None

    def _load_model(self):
        if TextEmbedding is None:
            raise RuntimeError("fastembed is not installed. Please run `pip install fastembed`.")
        if self._model is None:
            # 使用配置中的缓存路径和模型名称；device 仅做 best-effort（不支持则自动回退）
            try:
                if self._device in ("cuda", "mps"):
                    providers = ["CUDAExecutionProvider"] if self._device == "cuda" else ["CoreMLExecutionProvider"]
                    self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir, providers=providers)  # type: ignore[call-arg]
                else:
                    self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
            except TypeError:
                # fastembed 版本差异：可能不支持 providers 参数
                self._logger.warning("fastembed TextEmbedding 不支持 providers 参数，已回退到默认 provider。")
                self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)

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

