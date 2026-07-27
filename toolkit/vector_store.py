"""AgentForge — 向量知识库

使用 ChromaDB（文件级向量数据库）+ OpenAI 兼容的 Embedding API。
禁用 ChromaDB 默认 ONNX 模型（79MB），通过 API 自己提供向量。
"""

import json, hashlib
from pathlib import Path
from typing import Callable
import chromadb
from chromadb.config import Settings


class VectorStore:
    """向量知识库 — 使用 API 做 Embedding，不下载 ChromaDB 的 ONNX 模型"""

    def __init__(
        self,
        collection_name: str = "agentforge_rag",
        api_key: str = "",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_model: str = "text-embedding-v3",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.embedding_model = embedding_model
        self._ready = False

        # ChromaDB 持久化目录
        persist_dir = Path.home() / ".cache" / "agentforge" / "chroma"
        persist_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            # 使用空的 embedding 函数 — 我们通过 API 自己提供向量
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
        except Exception as e:
            print(f"[VectorStore] ChromaDB 初始化失败: {e}")
            self._ready = False

    @property
    def is_ready(self) -> bool: return self._ready

    @property
    def count(self) -> int:
        if not self._ready: return 0
        return self._collection.count()

    def _get_embedding(self, text: str) -> list[float]:
        """调用 Embedding API 获取向量（阿里百炼 DashScope / OpenAI 兼容）"""
        if not self.api_key:
            raise ValueError("Embedding API Key 未配置")
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.embeddings.create(input=text, model=self.embedding_model)
        return resp.data[0].embedding
    def add_documents(self, texts: list[str], metadatas: list[dict] | None = None, batch_size: int = 10):
        """批量添加文档 — 使用 API 批量预计算向量，绕过 ChromaDB 内部嵌入"""
        if not self._ready or not texts:
            return
        ids = [hashlib.md5(t.encode()).hexdigest()[:16] for t in texts]
        meta_list = (metadatas or [{"source": "unknown"} for _ in texts])
        while len(meta_list) < len(texts):
            meta_list.append({"source": "unknown"})
        try:
            # 批量调用 Embedding API（避免逐个调用）
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                resp = self._embed_client().embeddings.create(
                    input=batch, model=self.embedding_model
                )
                embeddings.extend([d.embedding for d in resp.data])
            self._collection.add(
                documents=texts, embeddings=embeddings,
                metadatas=meta_list[:len(texts)], ids=ids,
            )
        except Exception as e:
            print(f"[VectorStore] 添加文档失败: {e}")

    def _embed_client(self):
        """获取 Embedding API 客户端（延迟初始化）"""
        from openai import OpenAI
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, str, str, float]]:
        """向量检索 → [(id, text, source, score), ...]"""
        if not self._ready or self.count == 0: return []
        try:
            qv = self._get_embedding(query)
            results = self._collection.query(query_embeddings=[qv], n_results=min(top_k, self.count))
        except Exception as e:
            print(f"[VectorStore] 检索失败: {e}"); return []
        if not results.get("ids") or not results["ids"][0]: return []
        out = []
        for i in range(len(results["ids"][0])):
            did = results["ids"][0][i]
            text = results["documents"][0][i] if results.get("documents") else ""
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            score = results["distances"][0][i] if results.get("distances") else 0
            out.append((did, text, meta.get("source", "unknown"), round(1.0 - score, 4)))
        return out

    def hybrid_search(self, query: str, keyword_fn: Callable | None = None, top_k: int = 5) -> list[tuple[str, str, str, float]]:
        """混合检索：向量 + 关键词 + RRF 融合"""
        vec = self.search(query, top_k=top_k * 2) if self._ready else []
        kw = []
        if keyword_fn:
            for item in keyword_fn(query, top_k=top_k * 2):
                kw.append(item if len(item) >= 4 else (item[0], item[1], item[2], 0.0))
        if not vec: return kw[:top_k]
        if not kw: return vec[:top_k]
        K = 60; scores = {}
        for rank, (did, text, src, _) in enumerate(vec, 1):
            scores[did] = scores.get(did, {"text": text, "source": src, "rrf": 0.0})
            scores[did]["rrf"] += 1 / (K + rank)
        for rank, (did, text, src, _) in enumerate(kw, 1):
            scores[did] = scores.get(did, {"text": text, "source": src, "rrf": 0.0})
            scores[did]["rrf"] += 1 / (K + rank)
        return [(did, info["text"], info["source"], round(info["rrf"], 4))
                for did, info in sorted(scores.items(), key=lambda x: -x[1]["rrf"])[:top_k]]

    def clear(self):
        if self._ready:
            try: self._collection.delete(where={})
            except Exception: pass
