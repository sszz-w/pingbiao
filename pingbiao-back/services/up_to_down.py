"""从上往下查找：通过 all.txt 定位页码区间 → 查询汇总 txt → 精确定位单页 → 合并后与大模型对话"""
import asyncio
import re
from collections.abc import Callable
from pathlib import Path

from openai import AsyncOpenAI

from config import get_down_to_up_chunk_size, get_down_to_up_chunk_overlap
from prompts.templates import (
    UP_TO_DOWN_STEP1_PROMPT,
    UP_TO_DOWN_STEP2_PROMPT,
    UP_TO_DOWN_STEP3_PROMPT,
)

# 单次送入 LLM 的最大字符数，避免超出上下文
MAX_CONTENT_LEN = 12000


def _log(msg: str, log_cb: Callable[[str], None] | None) -> None:
    """输出日志：有回调则用回调，否则 print"""
    if log_cb:
        log_cb(msg)
    else:
        print(msg, flush=True)


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


def _parse_page_range(text: str) -> tuple[int, int] | None:
    """
    从 LLM 返回的文本中解析页码区间。
    支持格式：15～25、15-25、15-25页
    返回 (start, end) 或 None
    """
    text = text.strip()
    # 匹配 数字～数字 或 数字-数字
    m = re.search(r"(\d+)[～\-](\d+)", text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def _parse_page_list(text: str) -> list[int]:
    """
    从 LLM 返回的文本中解析页码列表。
    支持格式：16～21、21～24 或 16、17、18、19、20、21、22、23、24
    返回去重、排序的页码列表
    """
    pages: set[int] = set()
    text = text.strip()

    # 匹配区间：数字～数字 或 数字-数字
    for m in re.finditer(r"(\d+)[～\-](\d+)", text):
        start, end = int(m.group(1)), int(m.group(2))
        for p in range(min(start, end), max(start, end) + 1):
            pages.add(p)

    # 匹配单个数字
    for m in re.finditer(r"\b(\d+)\b", text):
        pages.add(int(m.group(1)))

    return sorted(pages)


def _parse_chunk_filename(name: str) -> tuple[int, int] | None:
    """
    解析汇总文件名，如 "11～21.txt" -> (11, 21)
    """
    stem = Path(name).stem
    m = re.match(r"^(\d+)[～\-](\d+)$", stem)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def _chunks_overlap(
    chunk_start: int, chunk_end: int, query_start: int, query_end: int
) -> bool:
    """判断汇总文件区间与查询区间是否有交集"""
    return chunk_start <= query_end and chunk_end >= query_start


async def up_to_down(
    folder_path: str | Path,
    query_content: str,
    output_format: str,
    api_key: str,
    base_url: str,
    model: str,
    log_callback: Callable[[str], None] | None = None,
    result_callback: Callable[[str], None] | None = None,
    json_format_instruction: str | None = None,
) -> int:
    """
    从上往下查找：通过 all.txt 定位页码区间，查询对应汇总 txt，
    精确定位单页 txt，合并后与大模型对话得到答案。

    Args:
        folder_path: 文件夹路径 A（需已运行 down_to_up，存在 A/summary）
        query_content: 要查询的内容
        output_format: 期望回复格式，"list"（列表）、"paragraph"（普通段落）或 "json"
        api_key: LLM API Key
        base_url: LLM API 基础地址
        model: 模型名称
        log_callback: 可选，用于实时输出日志
        result_callback: 可选，成功时传入最终答案
        json_format_instruction: 当 output_format 为 json 且本参数非空时，替换 Step3 中默认的 JSON 输出说明

    Returns:
        1: 成功
        0: 失败
    """
    folder = Path(folder_path)
    if not folder.exists():
        _log(f"❌ 文件夹不存在: {folder}", log_callback)
        return 0
    if not folder.is_dir():
        _log(f"❌ 路径不是文件夹: {folder}", log_callback)
        return 0

    summary_dir = folder / "summary"
    all_path = summary_dir / "all.txt"
    if not all_path.exists():
        _log(f"❌ 未找到 {all_path}，请先运行 down_to_up", log_callback)
        return 0

    try:
        all_content = all_path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as e:
        _log(f"❌ 读取 all.txt 失败: {e}", log_callback)
        return 0

    if not all_content:
        _log("❌ all.txt 为空", log_callback)
        return 0

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    # Step1: 阅读 all.txt，获取页码区间
    _log("🔄 步骤1：阅读总览，定位页码区间...", log_callback)
    step1_prompt = UP_TO_DOWN_STEP1_PROMPT.format(
        all_summary=all_content[:MAX_CONTENT_LEN],
        query_content=query_content,
    )
    try:
        step1_response = await _call_llm(client, model, step1_prompt)
    except Exception as e:
        _log(f"❌ 步骤1 LLM 调用失败: {e}", log_callback)
        return 0

    page_range = _parse_page_range(step1_response)
    if not page_range:
        _log(f"❌ 无法解析页码区间，LLM 返回: {step1_response[:200]}", log_callback)
        return 0

    query_start, query_end = page_range
    _log(f"  ✓ 定位到页码区间 {query_start}～{query_end}", log_callback)

    # Step2: 筛选并读取与区间有交集的汇总文件
    chunk_files = [
        f
        for f in summary_dir.iterdir()
        if f.is_file()
        and f.name != "all.txt"
        and f.suffix.lower() == ".txt"
    ]
    overlapping_chunks: list[tuple[Path, int, int]] = []
    for f in chunk_files:
        parsed = _parse_chunk_filename(f.name)
        if parsed and _chunks_overlap(parsed[0], parsed[1], query_start, query_end):
            overlapping_chunks.append((f, parsed[0], parsed[1]))

    overlapping_chunks.sort(key=lambda x: x[1])
    if not overlapping_chunks:
        _log(f"❌ 未找到与区间 {query_start}～{query_end} 有交集的汇总文件", log_callback)
        return 0

    chunk_parts: list[str] = []
    for f, c_start, c_end in overlapping_chunks:
        try:
            content = f.read_text(encoding="utf-8", errors="replace").strip()
            chunk_parts.append(f"【第 {c_start}～{c_end} 页摘要】\n{content}")
        except Exception as e:
            _log(f"❌ 读取 {f.name} 失败: {e}", log_callback)
            return 0

    chunk_summaries_text = "\n\n".join(chunk_parts)
    if len(chunk_summaries_text) > MAX_CONTENT_LEN:
        chunk_summaries_text = chunk_summaries_text[:MAX_CONTENT_LEN] + "\n\n（内容过长，已截断）"

    _log("🔄 步骤2：查询汇总文件，精确定位页码...", log_callback)
    step2_prompt = UP_TO_DOWN_STEP2_PROMPT.format(
        chunk_summaries=chunk_summaries_text,
        query_content=query_content,
    )
    try:
        step2_response = await _call_llm(client, model, step2_prompt)
    except Exception as e:
        _log(f"❌ 步骤2 LLM 调用失败: {e}", log_callback)
        return 0

    page_list = _parse_page_list(step2_response)
    if not page_list:
        _log(f"❌ 无法解析页码列表，LLM 返回: {step2_response[:200]}", log_callback)
        return 0

    _log(f"  ✓ 精确定位到页码: {page_list}", log_callback)

    # Step3: 读取单页 txt，合并后与大模型对话
    merged_parts: list[str] = []
    for p in page_list:
        page_file = folder / f"{p}.txt"
        if not page_file.exists():
            _log(f"  ⚠ 跳过不存在的文件 {p}.txt", log_callback)
            continue
        try:
            content = page_file.read_text(encoding="utf-8", errors="replace").strip()
            merged_parts.append(f"--- 第 {p} 页 ---\n{content}")
        except Exception as e:
            _log(f"❌ 读取 {p}.txt 失败: {e}", log_callback)
            return 0

    if not merged_parts:
        _log("❌ 未能读取任何单页文件", log_callback)
        return 0

    merged_content = "\n\n".join(merged_parts)
    if len(merged_content) > MAX_CONTENT_LEN:
        merged_content = merged_content[:MAX_CONTENT_LEN] + "\n\n（内容过长，已截断）"

    fmt = output_format.lower()
    if fmt == "list":
        format_instruction = "以列表形式输出，每条一行。"
    elif fmt == "json":
        if json_format_instruction and json_format_instruction.strip():
            format_instruction = json_format_instruction.strip()
        else:
            format_instruction = "以 JSON 格式输出，结构清晰、字段明确。"
    else:
        format_instruction = "以普通段落形式输出。"

    _log("🔄 步骤3：合并原文，生成最终答案...", log_callback)
    step3_prompt = UP_TO_DOWN_STEP3_PROMPT.format(
        merged_content=merged_content,
        query_content=query_content,
        format_instruction=format_instruction,
    )
    try:
        final_answer = await _call_llm(client, model, step3_prompt)
    except Exception as e:
        _log(f"❌ 步骤3 LLM 调用失败: {e}", log_callback)
        return 0

    _log("✅ 查找完成", log_callback)
    if result_callback:
        result_callback(final_answer)
    return 1

