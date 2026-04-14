"""PDF 上传接口：接收 PDF 文件，后台解析，通过统一 WebSocket 实时推送日志"""
import asyncio
import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, UploadFile

from config import get_base_dir
from services.deal_pdf import deal_pdf, deal_pdf2
from services.ws_manager import is_task_registered, send_json_to_task

router = APIRouter()

_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _normalize_task_id(raw: str) -> str | None:
    tid = raw.strip()
    if not tid or not _TASK_ID_RE.match(tid):
        return None
    return tid


def _validate_base_url(url: str) -> bool:
    u = url.strip()
    return u.startswith(("http://", "https://")) and len(u) <= 2048


def _run_deal_pdf_in_background(
    pdf_path: Path,
    task_id: str,
    *,
    pdf_name: str | None = None,
    base_url: str,
    api_token: str,
    model_name: str,
) -> None:
    """在后台运行 deal_pdf，将日志通过统一 WebSocket 推送"""

    def log_callback(msg: str) -> None:
        """同步回调 → 调度异步 WebSocket 推送"""
        asyncio.create_task(
            send_json_to_task(task_id, {"type": "pdf_log", "message": msg})
        )

    async def _run() -> None:
        try:
            result = await deal_pdf(
                pdf_path,
                log_callback=log_callback,
                task_id=task_id,
                pdf_name=pdf_name,
                api_key=api_token,
                base_url=base_url.strip(),
                model=model_name.strip(),
            )
            await send_json_to_task(
                task_id,
                {"type": "task_done", "task_id": task_id, "result": result},
            )
        except Exception as e:
            await send_json_to_task(
                task_id,
                {"type": "error", "message": f"后台异常: {e}"},
            )

    asyncio.create_task(_run())


@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(..., description="PDF 原文件"),
    task_id: str = Form(
        ...,
        description="由 verify-model 返回的 taskId",
    ),
    base_url: str = Form(..., description="大模型 OpenAI 兼容 API 的 base_url，如 https://api.openai.com/v1"),
    api_token: str = Form(..., description="API Key / Token"),
    model_name: str = Form(..., description="模型名称"),
) -> dict:
    """
    上传 PDF 文件接口。

    - 输入（multipart/form-data）:
      - file: PDF 文件
      - task_id: 由 verify-model 返回的 taskId
      - base_url: 大模型 API 基础地址
      - api_token: API 凭证
      - model_name: 模型名
    - 输出: {"result": 1, "task_id": "..."} 或 {"result": 0, "error": "..."}
    - 建议流程: 先 POST verify-model 获取 taskId → 连接 WS /api/ws/pdf-process/{taskId} → POST 本接口开始处理
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"result": 0, "error": "invalid_pdf"}

    tid = _normalize_task_id(task_id)
    if not tid:
        return {"result": 0, "error": "invalid_task_id"}

    base_url_s = base_url.strip()
    if not _validate_base_url(base_url_s):
        return {"result": 0, "error": "invalid_base_url"}

    token_s = api_token.strip()
    model_s = model_name.strip()
    if not token_s:
        return {"result": 0, "error": "empty_api_token"}
    if not model_s:
        return {"result": 0, "error": "empty_model_name"}

    try:
        content = await file.read()
        if not content:
            return {"result": 0, "error": "empty_file"}

        base_dir = get_base_dir()
        temp_dir = base_dir / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in file.filename)
        pdf_path = temp_dir / f"{safe_name}_{tid}.pdf"
        pdf_path.write_bytes(content)

        _run_deal_pdf_in_background(
            pdf_path,
            tid,
            base_url=base_url_s,
            api_token=token_s,
            model_name=model_s,
        )

        return {"result": 1, "task_id": tid}
    except Exception:
        return {"result": 0, "error": "upload_failed"}


# ---------- 批量上传多个投标 PDF ----------


def _run_many_pdfs_in_background(
    pdf_items: list[tuple[Path, str]],
    task_id: str,
    *,
    base_url: str,
    api_token: str,
    model_name: str,
) -> None:
    """后台逐个处理多个 PDF，每个 OCR 完成后通过 WS 推送 ocr_done"""

    def make_log_callback(name: str):
        def log_callback(msg: str) -> None:
            asyncio.create_task(
                send_json_to_task(task_id, {
                    "type": "pdf_log",
                    "pdf_name": name,
                    "message": msg,
                })
            )
        return log_callback

    async def _run() -> None:
        success_count = 0
        total = len(pdf_items)
        completed_pdfs = []

        for idx, (pdf_path, original_name) in enumerate(pdf_items, 1):
            await send_json_to_task(task_id, {
                "type": "pdf_progress",
                "current": idx,
                "total": total,
                "pdf_name": original_name,
            })
            try:
                result, parent_dir = await deal_pdf2(
                    pdf_path,
                    log_callback=make_log_callback(original_name),
                    task_id=task_id,
                    pdf_name=original_name,
                    api_key=api_token,
                    base_url=base_url.strip(),
                    model=model_name.strip(),
                )
                if result == 1:
                    success_count += 1
                    completed_pdfs.append({
                        "pdf_name": original_name,
                        "parent_dir": parent_dir,
                    })
            except Exception as e:
                await send_json_to_task(task_id, {
                    "type": "error",
                    "pdf_name": original_name,
                    "message": f"处理失败: {e}",
                })

        await send_json_to_task(task_id, {
            "type": "all_pdfs_done",
            "task_id": task_id,
            "total": total,
            "success": success_count,
            "completed_pdfs": completed_pdfs,
        })

    asyncio.create_task(_run())


@router.post("/upload-many-pdfs")
async def upload_many_pdfs(
    files: List[UploadFile] = File(..., description="多个投标 PDF 文件"),
    task_id: str = Form(..., description="由 verify-model 返回的 taskId"),
    base_url: str = Form(..., description="大模型 API 基础地址"),
    api_token: str = Form(..., description="API Key / Token"),
    model_name: str = Form(..., description="模型名称"),
) -> dict:
    """
    批量上传多个投标 PDF 文件接口。

    - 输入（multipart/form-data）:
      - files: 多个 PDF 文件
      - task_id: 由 verify-model 返回的 taskId
      - base_url, api_token, model_name: 大模型配置
    - 输出: {"result": 1, "task_id": "...", "file_count": N} 或 {"result": 0, "error": "..."}
    - 后台逐个处理每个 PDF（pdf_to_jpg → OCR → down_to_up 汇总）

    WebSocket 消息类型:
      - {"type": "pdf_progress", "current": 1, "total": 3, "pdf_name": "..."} — 当前处理进度
      - {"type": "pdf_log", "pdf_name": "...", "message": "..."} — 单个 PDF 的处理日志
      - {"type": "ocr_done", "pdf_name": "...", "parent_dir": "/abs/path"} — 单个 PDF OCR 完成
      - {"type": "error", "pdf_name": "...", "message": "..."} — 单个 PDF 处理失败
      - {"type": "all_pdfs_done", "task_id": "...", "total": 3, "success": 3} — 全部完成
    """
    tid = _normalize_task_id(task_id)
    if not tid:
        return {"result": 0, "error": "invalid_task_id"}

    if not is_task_registered(tid):
        return {"result": 0, "error": "task_not_registered"}

    base_url_s = base_url.strip()
    if not _validate_base_url(base_url_s):
        return {"result": 0, "error": "invalid_base_url"}

    token_s = api_token.strip()
    model_s = model_name.strip()
    if not token_s:
        return {"result": 0, "error": "empty_api_token"}
    if not model_s:
        return {"result": 0, "error": "empty_model_name"}

    if not files:
        return {"result": 0, "error": "no_files"}

    # 校验所有文件为 PDF 并保存到临时目录
    base_dir = get_base_dir()
    temp_dir = base_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    pdf_items: list[tuple[Path, str]] = []
    for idx, f in enumerate(files):
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            return {"result": 0, "error": "invalid_pdf", "file": f.filename or "unknown"}
        try:
            content = await f.read()
            if not content:
                return {"result": 0, "error": "empty_file", "file": f.filename}
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in f.filename)
            pdf_path = temp_dir / f"{safe_name}_{tid}_{idx}.pdf"
            pdf_path.write_bytes(content)
            pdf_items.append((pdf_path, f.filename))
        except Exception:
            return {"result": 0, "error": "upload_failed", "file": f.filename}

    _run_many_pdfs_in_background(
        pdf_items,
        tid,
        base_url=base_url_s,
        api_token=token_s,
        model_name=model_s,
    )

    return {"result": 1, "task_id": tid, "file_count": len(pdf_items)}
