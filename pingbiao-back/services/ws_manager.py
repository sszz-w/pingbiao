"""
WebSocket 连接管理器 — 统一 WebSocket 通道

- 验证成功后生成 taskId，前端连接 ws://host/api/ws/pdf-process/{taskId}
- 连接保持持久，供 upload-pdf、get-clause、upload-many-pdfs、analysis-clause 等接口复用推送
"""
from __future__ import annotations

import json

from fastapi import WebSocket
from starlette.websockets import WebSocketState


# 已注册的 taskId（由 verify-model 成功时创建）
_registered_tasks: set[str] = set()

# task_id -> WebSocket 活跃连接
_connections: dict[str, WebSocket] = {}


def register_task(task_id: str) -> None:
    """验证成功后注册 taskId，允许前端连接"""
    _registered_tasks.add(task_id)


def unregister_task(task_id: str) -> None:
    """移除 taskId 注册"""
    _registered_tasks.discard(task_id)
    _connections.pop(task_id, None)


def is_task_registered(task_id: str) -> bool:
    """检查 taskId 是否已注册（可连接）"""
    return task_id in _registered_tasks


def set_connection(task_id: str, websocket: WebSocket) -> None:
    """保存 WebSocket 连接"""
    _connections[task_id] = websocket


def get_connection(task_id: str) -> WebSocket | None:
    """获取 taskId 对应的 WebSocket 连接"""
    return _connections.get(task_id)


def remove_connection(task_id: str) -> None:
    """移除连接"""
    _connections.pop(task_id, None)


async def send_to_task(task_id: str, message: str) -> bool:
    """
    向指定 taskId 的 WebSocket 发送纯文本消息。
    返回 True 表示发送成功，False 表示连接不存在或发送失败。
    """
    ws = get_connection(task_id)
    if ws is None:
        return False
    if ws.client_state != WebSocketState.CONNECTED:
        remove_connection(task_id)
        return False
    try:
        await ws.send_text(message)
        return True
    except Exception:
        remove_connection(task_id)
        return False


async def send_json_to_task(task_id: str, data: dict) -> bool:
    """
    向指定 taskId 的 WebSocket 发送结构化 JSON 消息。
    内部 json.dumps + send_text，供各业务接口统一推送。
    返回 True 表示发送成功，False 表示连接不存在或发送失败。
    """
    return await send_to_task(task_id, json.dumps(data, ensure_ascii=False))
