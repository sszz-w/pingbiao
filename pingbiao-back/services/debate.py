"""AI 双代理辩论引擎"""
import json
import re
from typing import AsyncGenerator
from openai import AsyncOpenAI
from models.schemas import Clause, Chunk, DebateEvent
from prompts.templates import SUPPORT_PROMPT, CHALLENGE_PROMPT, ARBITRATOR_PROMPT


def _extract_json(text: str) -> dict:
    """从 LLM 返回文本中提取 JSON"""
    # 先尝试直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取第一个 {...}
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 LLM 返回中提取 JSON: {text[:200]}")


async def _call_llm(client: AsyncOpenAI, model: str, prompt: str) -> str:
    """调用 LLM 并返回文本"""
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


async def debate_and_score(
    client: AsyncOpenAI,
    model: str,
    clause: Clause,
    chunks: list[Chunk],
) -> AsyncGenerator[DebateEvent, None]:
    """
    AI 双代理辩论打分（支持方 → 质疑方 → 仲裁）

    Yields:
        DebateEvent 事件流
    """
    chunks_text = "\n---\n".join(c.content for c in chunks) if chunks else "（未检索到相关内容）"

    # === 1. 支持方 ===
    support_prompt = SUPPORT_PROMPT.format(
        clause_no=clause.no,
        clause_desc=clause.desc,
        clause_score=clause.score,
        chunks=chunks_text,
    )

    try:
        support_raw = await _call_llm(client, model, support_prompt)
        support_data = _extract_json(support_raw)
        support_score = float(support_data.get("score", clause.score * 0.7))
        support_reason = str(support_data.get("reason", support_raw))
    except Exception as e:
        support_score = clause.score * 0.7
        support_reason = f"支持方分析出错，使用默认评分: {e}"

    yield DebateEvent(
        type="debate",
        role="support",
        content=support_reason,
    )

    # === 2. 质疑方 ===
    challenge_prompt = CHALLENGE_PROMPT.format(
        clause_no=clause.no,
        clause_desc=clause.desc,
        clause_score=clause.score,
        chunks=chunks_text,
        support_score=support_score,
        support_reason=support_reason,
    )

    try:
        challenge_raw = await _call_llm(client, model, challenge_prompt)
        challenge_data = _extract_json(challenge_raw)
        challenge_text = str(challenge_data.get("challenge", challenge_raw))
        challenge_score = float(challenge_data.get("suggested_score", support_score))
    except Exception as e:
        challenge_text = f"质疑方分析出错: {e}"
        challenge_score = support_score

    yield DebateEvent(
        type="debate",
        role="challenge",
        content=challenge_text,
    )

    # === 3. 仲裁 ===
    arbitrator_prompt = ARBITRATOR_PROMPT.format(
        clause_no=clause.no,
        clause_desc=clause.desc,
        clause_score=clause.score,
        chunks=chunks_text,
        support_score=support_score,
        support_reason=support_reason,
        challenge=challenge_text,
        challenge_score=challenge_score,
    )

    try:
        arb_raw = await _call_llm(client, model, arbitrator_prompt)
        arb_data = _extract_json(arb_raw)
        final_score = float(arb_data.get("score", (support_score + challenge_score) / 2))
        final_reason = str(arb_data.get("reason", arb_raw))
    except Exception as e:
        final_score = round((support_score + challenge_score) / 2, 1)
        final_reason = f"仲裁分析出错，取双方均值: {e}"

    yield DebateEvent(
        type="score",
        score=final_score,
        reason=final_reason,
    )
