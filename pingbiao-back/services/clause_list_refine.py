"""条款列表多轮 LLM 精炼：过滤总则行、字段整理、默认合格制评分标准。"""
from __future__ import annotations

from collections.abc import Callable

from openai import AsyncOpenAI

from prompts.templates import CLAUSE_LIST_REFINE_FILTER_PROMPT, CLAUSE_LIST_REFINE_POLISH_PROMPT

ParseRowsFn = Callable[[str], tuple[list[dict[str, str]], str | None]]

# 文中未给出具体评分细则时，合格性类条款的默认评分标准
DEFAULT_PASS_FAIL_SCORING = "满足得 100 分，不满足的 0 分"

_REFINE_TEMPERATURE = 0.2


async def _call_llm_json_array(
    client: AsyncOpenAI,
    model: str,
    user_content: str,
) -> str:
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": user_content}],
        temperature=_REFINE_TEMPERATURE,
    )
    return response.choices[0].message.content.strip()


def apply_default_scoring(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """评分标准为空时填入默认合格制文案。"""
    out: list[dict[str, str]] = []
    for row in rows:
        r = dict(row)
        if not (r.get("评分标准") or "").strip():
            r["评分标准"] = DEFAULT_PASS_FAIL_SCORING
        out.append(r)
    return out


async def refine_clause_list_filter(
    client: AsyncOpenAI,
    model: str,
    rows: list[dict[str, str]],
    parse_rows: ParseRowsFn,
    on_parse_fail: Callable[[str], None] | None = None,
) -> list[dict[str, str]]:
    """
    轮 1：删除分值构成、基准价方法、偏差率公式等非逐条评审条款。
    解析失败时回退为输入 rows。
    """
    import json

    payload = json.dumps(rows, ensure_ascii=False)
    prompt = CLAUSE_LIST_REFINE_FILTER_PROMPT.format(clause_list_json=payload)
    raw = await _call_llm_json_array(client, model, prompt)
    parsed, err = parse_rows(raw)
    if err:
        if on_parse_fail:
            on_parse_fail(f"条款列表精炼(过滤)解析失败，使用初稿: {err}")
        return list(rows)
    return parsed


async def refine_clause_list_polish(
    client: AsyncOpenAI,
    model: str,
    rows: list[dict[str, str]],
    parse_rows: ParseRowsFn,
    on_parse_fail: Callable[[str], None] | None = None,
) -> list[dict[str, str]]:
    """
    轮 2：字段整理、补删漏网总则行；不改变已有非空评分标准的常规语义。
    解析失败时回退为输入 rows。
    """
    import json

    payload = json.dumps(rows, ensure_ascii=False)
    prompt = CLAUSE_LIST_REFINE_POLISH_PROMPT.format(clause_list_json=payload)
    raw = await _call_llm_json_array(client, model, prompt)
    parsed, err = parse_rows(raw)
    if err:
        if on_parse_fail:
            on_parse_fail(f"条款列表精炼(整理)解析失败，沿用上一轮: {err}")
        return list(rows)
    return parsed


async def run_clause_list_refinement(
    client: AsyncOpenAI,
    model: str,
    rows: list[dict[str, str]],
    parse_rows: ParseRowsFn,
    on_parse_fail: Callable[[str], None] | None = None,
) -> list[dict[str, str]]:
    """过滤 -> 默认评分标准 -> 整理。"""
    filtered = await refine_clause_list_filter(
        client, model, rows, parse_rows, on_parse_fail
    )
    with_default = apply_default_scoring(filtered)
    polished = await refine_clause_list_polish(
        client, model, with_default, parse_rows, on_parse_fail
    )
    # 轮 2 可能引入新的空评分标准
    return apply_default_scoring(polished)
