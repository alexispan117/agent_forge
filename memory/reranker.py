"""AgentForge — 重排序（Rerank）

基于得分的重排序，融合原始分和位置信息。
"""

from typing import Any


def rerank_by_hybrid(
    candidates: list[tuple[str, str, str, float] | tuple[str, str, float]],
    top_k: int = 5,
) -> list[tuple[str, str, str, float]]:
    """基于得分的重排序（融合原始分 + 位置信息）

    支持 4 元组 (id, text, source, score) 和 3 元组 (id, text, score)。
    """
    if not candidates:
        return []

    # 统一为 4 元组
    norm = []
    for c in candidates:
        if len(c) == 4:
            norm.append(c)
        else:
            norm.append((c[0], c[1], "", c[2]))

    norm.sort(key=lambda x: -x[3])

    # 位置加权
    weighted = []
    for i, (doc_id, text, source, score) in enumerate(norm):
        pos_weight = 1.0 / (1 + i * 0.1)
        weighted.append((doc_id, text, source, score * pos_weight))

    weighted.sort(key=lambda x: -x[3])
    return weighted[:top_k]
