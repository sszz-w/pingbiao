"""关键词检索服务"""
import jieba
from models.schemas import Chunk

# 中文停用词（精简版）
STOP_WORDS = set(
    "的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 "
    "自己 这 他 她 它 们 那 些 什么 怎么 如果 因为 所以 但是 而且 或者 以及 对于 关于 "
    "可以 应该 需要 能够 进行 通过 根据 按照 其中 以下 以上 等 及 与 为 之 其 该 本 "
    "中 大 小 多 少 个 各 每 某 此 另 其他".split()
)


def retrieve_chunks(query: str, chunks: list[Chunk], top_k: int = 5) -> list[Chunk]:
    """
    基于 jieba 分词的关键词检索

    Args:
        query: 查询文本（条款描述）
        chunks: 投标切片列表
        top_k: 返回前 k 个最相关的切片

    Returns:
        按相关性排序的切片列表
    """
    if not chunks:
        return []

    # 对查询文本分词，去停用词
    keywords = [
        w for w in jieba.cut(query)
        if w.strip() and len(w.strip()) > 1 and w.strip() not in STOP_WORDS
    ]

    if not keywords:
        return chunks[:top_k]

    # 对每个 chunk 计算关键词命中数
    scored = []
    for chunk in chunks:
        hit_count = sum(1 for kw in keywords if kw in chunk.content)
        scored.append((hit_count, chunk))

    # 按命中数降序排序
    scored.sort(key=lambda x: x[0], reverse=True)

    return [chunk for _, chunk in scored[:top_k]]
