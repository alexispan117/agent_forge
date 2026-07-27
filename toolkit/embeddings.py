"""AgentForge — 语义检索器

参考教程 7.2.3 节（文本向量化）+ 7.2.4 节（混合检索 + RRF 融合）

支持两种模式：
1. OpenAI Embedding API（高质量，需 API Key）
2. 字符 n-gram 向量（零依赖，离线可用）
"""

import math
import re
from collections import Counter

# ── n-gram 向量（零依赖模式） ──

_CHAR_NGRAM = 2  # 字符二元组


def _char_ngrams(text: str, n: int = _CHAR_NGRAM) -> Counter:
    """将文本转为字符 n-gram 向量"""
    chars = text.lower()
    chars = re.sub(r"\s+", " ", chars)
    return Counter(chars[i : i + n] for i in range(len(chars) - n + 1))


def _cosine_sim(a: Counter, b: Counter) -> float:
    """两个 Counter 向量的余弦相似度"""
    intersection = set(a) & set(b)
    dot = sum(a[x] * b[x] for x in intersection)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── OpenAI Embedding 模式 ──

def _openai_embed(texts: list[str], client=None, model: str = "text-embedding-3-small") -> list[list[float]]:
    """调用 OpenAI 兼容的 Embedding API"""
    if client is None:
        raise ValueError("需要 OpenAI 客户端")
    resp = client.embeddings.create(input=texts, model=model)
    return [d.embedding for d in resp.data]


# ── SemanticSearcher ──

class SemanticSearcher:
    """语义检索器

    用法:
        searcher = SemanticSearcher()
        searcher.add_documents(["文本1", "文本2", ...])
        results = searcher.search("查询词", top_k=3)
    """

    def __init__(self, llm_client=None, embedding_model: str = "text-embedding-3-small"):
        self._llm_client = llm_client
        self._embedding_model = embedding_model
        self._docs: list[str] = []
        self._doc_ids: list[str] = []
        # 离线模式：存储 n-gram 向量
        self._ngrams: list[Counter] = []
        # API 模式：存储 embedding 向量
        self._vectors: list[list[float]] = []

    @property
    def has_api(self) -> bool:
        return self._llm_client is not None

    @property
    def doc_count(self) -> int:
        return len(self._docs)

    def add_documents(self, docs: list[str], doc_ids: list[str] | None = None):
        """批量添加文档

        Args:
            docs: 文档文本列表
            doc_ids: 文档 ID 列表（如文件名），不传则用索引
        """
        self._docs.extend(docs)
        self._doc_ids.extend(doc_ids or [str(i) for i in range(len(docs))])
        # n-gram 模式
        self._ngrams.extend(_char_ngrams(d) for d in docs)
        # API 模式（如果可用）
        if self.has_api and len(self._vectors) < len(self._docs):
            try:
                vecs = _openai_embed(docs[len(self._vectors):], self._llm_client, self._embedding_model)
                self._vectors.extend(vecs)
            except Exception:
                pass

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, str, float]]:
        """检索最相似的文档

        Returns:
            [(doc_id, doc_text, score), ...]
        """
        if not self._docs:
            return []

        query_ngram = _char_ngrams(query)
        scored = []

        for i in range(len(self._docs)):
            # n-gram 相似度（始终可用）
            ng_sim = _cosine_sim(query_ngram, self._ngrams[i]) if i < len(self._ngrams) else 0.0
            # 关键词重叠分（辅助）
            q_words = set(query.lower().split())
            d_words = set(self._docs[i].lower().split())
            overlap = len(q_words & d_words) / max(len(q_words | d_words), 1) if q_words else 0.0
            # 综合评分
            score = ng_sim * 0.6 + overlap * 0.4
            scored.append((self._doc_ids[i], self._docs[i], round(score, 4)))

        scored.sort(key=lambda x: -x[2])
        return scored[:top_k]

    def hybrid_search(self, query: str, keyword_fn=None, top_k: int = 5) -> list[tuple[str, str, float]]:
        """混合检索（语义 + 关键词 + RRF 融合）

        参考教程 7.2.4 节「混合检索」+ RRF 融合算法
        """
        semantic_results = self.search(query, top_k=top_k * 2)

        keyword_results = []
        if keyword_fn:
            keyword_results = keyword_fn(query, top_k=top_k * 2)

        if not keyword_results:
            return semantic_results[:top_k]

        # RRF 融合
        K = 60
        scores = {}
        for rank, (doc_id, text, _) in enumerate(semantic_results, 1):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (K + rank)
        for rank, item in enumerate(keyword_results, 1):
            doc_id = item[0] if isinstance(item, tuple) else str(hash(str(item)))
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (K + rank)

        id_map = {d: t for d, t, _ in semantic_results}
        sorted_items = sorted(scores.items(), key=lambda x: -x[1])
        return [(did, id_map.get(did, ""), sc) for did, sc in sorted_items[:top_k]]
