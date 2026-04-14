"""从下往上汇总：按分组将 txt 文件合并后调用 LLM 摘要，最终生成总览"""
import asyncio
import re
from collections.abc import Callable
from pathlib import Path

from openai import AsyncOpenAI

from config import get_down_to_up_chunk_size, get_down_to_up_chunk_overlap
from prompts.templates import DOWN_TO_UP_CHUNK_PROMPT, DOWN_TO_UP_FINAL_PROMPT
from services.ws_manager import send_json_to_task

# 单次送入 LLM 的最大字符数，避免超出上下文
MAX_CONTENT_LEN = 12000
MAX_SUMMARIES_LEN = 16000


async def _log(msg: str, task_id: str | None, log_cb: Callable[[str], None] | None) -> None:
    """输出日志：优先通过 WebSocket 推送，其次用回调，否则 print"""
    if task_id:
        await send_json_to_task(task_id, {"type": "pdf_log", "message": msg})
    elif log_cb:
        log_cb(msg)
    else:
        print(msg, flush=True)


def _natural_sort_key(p: Path) -> list:
    """按文件名中的数字自然排序，如 1.txt, 2.txt, 10.txt"""
    parts = re.split(r"(\d+)", p.stem)
    return [int(x) if x.isdigit() else x.lower() for x in parts if x]


def _extract_page_num(p: Path) -> int | None:
    """从文件名提取页码数字，如 1.txt -> 1"""
    if p.stem.isdigit():
        return int(p.stem)
    return None


async def _call_llm(client: AsyncOpenAI, model: str, prompt: str) -> str:
    """调用 LLM 并返回文本"""
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


async def down_to_up(
    folder_path: str | Path,
    api_key: str,
    base_url: str,
    model: str,
    task_id: str | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> int:
    """
    从下往上汇总：将文件夹 A 下的 txt 文件按配置分组，逐组调用 LLM 摘要，
    保存分段摘要到 A/summary，最后合并生成 all.txt。

    Args:
        folder_path: 包含 txt 文件的文件夹路径
        api_key: LLM API Key
        base_url: LLM API 基础地址
        model: 模型名称
        task_id: 可选，WebSocket 连接标识，用于实时推送日志到前端
        log_callback: 可选，用于实时输出日志

    Returns:
        1: 成功
        0: 失败
    """
    folder = Path(folder_path)
    if not folder.exists():
        await _log(f"❌ 文件夹不存在: {folder}", task_id, log_callback)
        return 0
    if not folder.is_dir():
        await _log(f"❌ 路径不是文件夹: {folder}", task_id, log_callback)
        return 0

    txt_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".txt"]
    if not txt_files:
        await _log("⚠️ 文件夹中没有找到 txt 文件", task_id, log_callback)
        return 0

    sorted_files = sorted(txt_files, key=_natural_sort_key)
    chunk_size = get_down_to_up_chunk_size()
    chunk_overlap = get_down_to_up_chunk_overlap()
    summary_dir = folder / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    prev_summary = ""
    prev_start = 0
    prev_end = 0
    chunk_summaries: list[str] = []

    try:
        await _log(f"📊 找到 {len(sorted_files)} 个 txt 文件，chunk_size={chunk_size}，overlap={chunk_overlap}", task_id, log_callback)
        await _log("🔄 开始分段摘要...\n", task_id, log_callback)

        step = chunk_size
        group_size = chunk_size + chunk_overlap

        for start_idx in range(0, len(sorted_files), step):
            end_idx = min(start_idx + group_size, len(sorted_files))
            group_files = sorted_files[start_idx:end_idx]
            if not group_files:
                break

            first_file = group_files[0]
            last_file = group_files[-1]
            start_page = _extract_page_num(first_file) or (start_idx + 1)
            end_page = _extract_page_num(last_file) or end_idx

            # 合并组内文本，按页码标注
            parts: list[str] = []
            for f in group_files:
                page_num = _extract_page_num(f) or "?"
                try:
                    content = f.read_text(encoding="utf-8", errors="replace").strip()
                except Exception as e:
                    await _log(f"❌ 读取失败 {f.name}: {e}", task_id, log_callback)
                    return 0
                parts.append(f"--- 第 {page_num} 页 ---\n{content}")

            merged = "\n\n".join(parts)
            if len(merged) > MAX_CONTENT_LEN:
                merged = merged[:MAX_CONTENT_LEN] + "\n\n（内容过长，已截断）"

            prev_context = ""
            if prev_summary:
                prev_context = f"上一段摘要（第 {prev_start}～{prev_end} 页）：\n{prev_summary}\n\n"

            prompt_text = DOWN_TO_UP_CHUNK_PROMPT.format(
                prev_summary_context=prev_context,
                start_page=start_page,
                end_page=end_page,
                content=merged,
            )

            try:
                summary = await _call_llm(client, model, prompt_text)
            except Exception as e:
                await _log(f"❌ LLM 调用失败（第 {start_page}～{end_page} 页）: {e}", task_id, log_callback)
                return 0

            chunk_summaries.append(summary)
            prev_summary = summary
            prev_start = start_page
            prev_end = end_page

            out_name = f"{start_page}～{end_page}.txt"
            out_path = summary_dir / out_name
            out_path.write_text(summary, encoding="utf-8")
            await _log(f"  ✓ 已汇总 {out_name}", task_id, log_callback)

        if not chunk_summaries:
            await _log("❌ 未生成任何分段摘要", task_id, log_callback)
            return 0

        await _log("🔄 生成最终总览...", task_id, log_callback)
        summaries_text = "\n\n---\n\n".join(
            f"【第 {i + 1} 段】\n{s}" for i, s in enumerate(chunk_summaries)
        )
        if len(summaries_text) > MAX_SUMMARIES_LEN:
            summaries_text = summaries_text[:MAX_SUMMARIES_LEN] + "\n\n（内容过长，已截断）"

        final_prompt = DOWN_TO_UP_FINAL_PROMPT.format(summaries=summaries_text)
        try:
            all_summary = await _call_llm(client, model, final_prompt)
        except Exception as e:
            await _log(f"❌ 最终汇总 LLM 调用失败: {e}", task_id, log_callback)
            return 0

        all_path = summary_dir / "all.txt"
        all_path.write_text(all_summary, encoding="utf-8")
        await _log(f"  ✓ 已汇总 all.txt\n✅ 全部完成", task_id, log_callback)
        return 1

    except Exception as e:
        await _log(f"❌ 处理异常: {e}", task_id, log_callback)
        return 0