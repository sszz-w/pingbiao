"""统一 WebSocket 端点：所有前后端实时消息走 /ws/pdf-process/{task_id}"""
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.ws_manager import (
    is_task_registered,
    remove_connection,
    set_connection,
)

router = APIRouter()


@router.websocket("/ws/{task_id}")
async def unified_websocket(websocket: WebSocket, task_id: str) -> None:
    """
    统一 WebSocket 端点。

    - 路径: /api/ws/pdf-process/{task_id}
    - task_id: 由 POST /api/verify-model 成功时返回的 taskId
    - 仅当 taskId 已通过 verify-model 注册时才接受连接，否则拒绝
    - 连接保持持久，供 upload-pdf 日志推送、get-clause、analysis-clause 等复用
    - 前端 → 后端消息格式: {"action": "ping"} 等 JSON
    - 后端 → 前端消息格式: {"type": "pong"} / {"type": "pdf_log", "message": "..."} 等 JSON
    """
    await websocket.accept()

    if not is_task_registered(task_id):
        await websocket.send_text(
            json.dumps({"type": "error", "message": "taskId 无效或未注册"}, ensure_ascii=False)
        )
        await websocket.close()
        return

    set_connection(task_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "消息格式无效，需 JSON"}, ensure_ascii=False)
                )
                continue

            action = msg.get("action")
            if action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            else:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": f"未知 action: {action}"}, ensure_ascii=False)
                )
    except WebSocketDisconnect:
        pass
    finally:
        remove_connection(task_id)
        try:
            await websocket.close()
        except Exception:
            pass
