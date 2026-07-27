"""Embedding 配置 dataclass

消除 Config 中 embedding 参数反复出现的 Data Clumps。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EmbeddingConfig:
    """Embedding API 配置（阿里百炼 DashScope / OpenAI 兼容）

    用法:
        cfg = EmbeddingConfig.from_dict(config.get("embedding", {}))
        store = VectorStore(**cfg.to_kwargs())
    """

    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "text-embedding-v3"

    @classmethod
    def from_dict(cls, d: dict) -> "EmbeddingConfig":
        return cls(
            api_key=d.get("api_key", ""),
            base_url=d.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            model=d.get("model", "text-embedding-v3"),
        )

    def to_kwargs(self) -> dict:
        return {"api_key": self.api_key, "base_url": self.base_url, "embedding_model": self.model}

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
