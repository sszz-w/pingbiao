"""会话存储服务 — 在 /api/run 和 /api/clause 之间共享解析结果"""
import uuid
from typing import Any

# 内存会话存储: {session_id: {"clauses": [...], "bids": {...}}}
_sessions: dict[str, dict[str, Any]] = {}


def create_session(clauses: list, bids: dict) -> str:
    """创建会话，缓存解析结果，返回 session_id"""
    session_id = uuid.uuid4().hex[:12]
    _sessions[session_id] = {
        "clauses": clauses,
        "bids": bids,
    }
    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    """根据 session_id 获取会话数据"""
    return _sessions.get(session_id)
