import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from models.schemas import ClauseListItem, ClauseRequest, ClauseResponse, ClauseScore
from services.session_store import get_session
from services.retriever import retrieve_chunks
from services.debate import debate_and_score
from services.clause_list_refine import (
    apply_default_scoring,
    refine_clause_list_filter,
    refine_clause_list_polish,
)
from services.up_to_down import up_to_down
from services.ws_manager import is_task_registered, send_json_to_task
from prompts.templates import (
    SUPPORT_PROMPT,
    CHALLENGE_PROMPT,
    ARBITRATOR_PROMPT,
)

router = APIRouter()


# ── 辩论专用 Prompt（V2版本，适配 up_to_down 提取的内容） ──

SUPPORT_PROMPT_V2 = """你是评标支持方 AI。根据评审条款和投标文件内容，为投标文件辩护并给出合理评分。

评审条款：
- 条款描述：{clause_describe}
- 评分规则：{score_criteria}
- 其他要求：{other_requirements}

投标文件相关内容摘录：
{bid_content}

初步分析：
- 初始评分：{initial_score}
- 思考过程：{thinking}

请站在支持方立场，客观评估投标文件的优势和符合性，给出你的评分（可以是数字、等级或文字）及理由。

输出 JSON 格式：
{{"score": "85", "reason": "投标文件中明确提供了...，符合条款要求，具备...优势。"}}

**仅输出 JSON，不要其他内容。**
"""

CHALLENGE_PROMPT_V2 = """你是评标质疑方 AI。根据评审条款和投标文件内容，对支持方的评分提出质疑或补充意见。

评审条款：
- 条款描述：{clause_describe}
- 评分规则：{score_criteria}
- 其他要求：{other_requirements}

投标文件相关内容摘录：
{bid_content}

支持方意见：
- 评分：{support_score}
- 理由：{support_reason}

请指出支持方评分中可能存在的问题：
- 是否遗漏了关键信息？
- 是否过度解读或低估了某些内容？
- 是否有更合理的评分建议？

输出 JSON 格式：
{{"challenge": "支持方忽略了...，实际上投标文件在...方面存在不足。", "suggested_score": "70"}}

**仅输出 JSON，不要其他内容。**
"""

ARBITRATOR_PROMPT_V2 = """你是评标仲裁方 AI。根据支持方与质疑方的辩论，给出最终分数及简要理由。

评审条款：
- 条款描述：{clause_describe}
- 评分规则：{score_criteria}
- 其他要求：{other_requirements}

投标文件相关内容摘录：
{bid_content}

支持方意见：
- 评分：{support_score}
- 理由：{support_reason}

质疑方意见：
- 质疑：{challenge_text}
- 建议评分：{challenge_score}

请综合双方意见，给出最终评分（可以是数字、等级或文字）、简要理由，以及投标文件中最相关的摘录。

输出 JSON 格式：
{{"score": "75", "reason": "综合考虑，投标文件基本满足要求，但存在...不足。", "excerpt": "投标文件第X页提到..."}}

**仅输出 JSON，不要其他内容。**
"""


# ── 辅助函数 ──

async def _call_llm_debate(client: AsyncOpenAI, model: str, prompt: str) -> str:
    """调用 LLM 并返回文本（用于辩论）"""
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def _extract_json_safe(text: str) -> dict:
    """从 LLM 返回文本中提取 JSON（容错版本）"""
    import re

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

    # 容错：返回空字典
    return {}


# ---------- 单条款评审 ----------

@router.post("/clause", response_model=ClauseResponse)
async def evaluate_clause(req: ClauseRequest):
    """
    单条款评审接口
    - 根据 session_id 获取已解析的投标数据
    - 对每个投标执行 AI 辩论打分
    - 返回 JSON 结果
    """
    # 获取 session
    session = get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    bids = session["bids"]
    client = AsyncOpenAI(api_key=req.api_key, base_url=req.api_base)

    scores: list[ClauseScore] = []

    for bid_id, data in bids.items():
        bid_name = data["file_name"]
        chunks = data["chunks"]

        # 检索相关切片
        relevant_chunks = retrieve_chunks(req.clause.desc, chunks, top_k=5)

        # AI 辩论打分
        final_score = None
        final_reason = None

        async for event in debate_and_score(client, req.model, req.clause, relevant_chunks):
            if event.type == "score":
                final_score = event.score
                final_reason = event.reason

        if final_score is not None:
            scores.append(ClauseScore(
                bid_id=bid_id,
                bid_name=bid_name,
                score=final_score,
                reason=final_reason or "",
            ))

    return ClauseResponse(
        clause_id=req.clause.id,
        clause_no=req.clause.no,
        scores=scores,
    )


# ---------- 获取条款列表（后台异步） ----------

# 用于从已汇总的文件夹中提取评审条款列表的查询内容
_CLAUSE_LIST_QUERY = (
    "请提取该文档中所有的评审条款、评分标准和评分细则，"
    "包括每个条款的编号、描述、分值和权重；"
    "形式评审、资格评审、响应性评审等可单独成行；评分细则每条一行。"
)

# Step3：强制输出为固定 JSON 数组，供前端表格展示
_CLAUSE_LIST_JSON_INSTRUCTION = """
仅输出一个 JSON 数组，不要 Markdown 代码块，不要任何前缀或后缀说明文字。
数组中每个元素必须是且只能是如下结构的对象（键名一字不差）：
{"条款描述": "...", "评分标准": "...", "其他要求": "..."}
字段含义：
- 条款描述：条款编号、条款名称/类别及要点概述（含子项时可合并为一段文字）。
- 评分标准：分值、权重、打分规则、计算公式等；若无打分信息填 ""。
- 其他要求：资格、形式、响应性、缺漏项处理等不便归入前两类的说明；若无填 ""。
每条独立的评审点或评分细则对应数组中的一个对象。
""".strip()

# 条款打分（投标文件）：Step3 强制输出为固定 JSON 对象
_ANALYSIS_CLAUSE_JSON_INSTRUCTION = """
仅输出一个 JSON 对象，不要 Markdown 代码块，不要任何前缀或后缀说明文字。
对象必须且只能包含以下三个键（键名一字不差）：
{"本地条款摘录": "...", "打分": "...", "思考过程": "..."}
字段含义：
- 本地条款摘录：从投标原文中摘录或归纳的、与当前待评审条款直接相关的响应要点（便于人工复核）；若无相关内容填 ""。
- 打分：依据用户给定的评分规则给出的结论；可为数字（如 85）、等级（如 合格）或简短文字；无法判断时填 ""。
- 思考过程：打分的依据、对照评分规则的推理步骤与说明；须完整、可追溯。
""".strip()


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _unwrap_top_level_list(payload: object) -> list | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and len(payload) == 1:
        v = next(iter(payload.values()))
        if isinstance(v, list):
            return v
    return None


def _coerce_clause_field(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _parse_clause_list_rows(raw: str) -> tuple[list[dict[str, str]], str | None]:
    """
    解析模型返回的 JSON 文本，归一为 ClauseListItem 字典列表。
    返回 (rows, error_message)；error_message 仅在解析失败或无法得到列表时非空。
    """
    text = _strip_json_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return [], f"条款列表 JSON 解析失败: {e}"

    rows_raw = _unwrap_top_level_list(data)
    if rows_raw is None:
        return [], "条款列表 JSON 根节点不是数组（且无法从单键对象中解包出数组）"

    out: list[dict[str, str]] = []
    for item in rows_raw:
        if not isinstance(item, dict):
            continue
        row = ClauseListItem(
            条款描述=_coerce_clause_field(item.get("条款描述")),
            评分标准=_coerce_clause_field(item.get("评分标准")),
            其他要求=_coerce_clause_field(item.get("其他要求")),
        ).model_dump()
        out.append(row)

    if not out and rows_raw:
        return [], "条款列表数组中无有效对象（元素需为含固定键的对象）"

    return out, None


def _parse_analysis_clause_result(raw: str) -> tuple[dict[str, str] | None, str | None]:
    """
    解析模型返回的条款打分 JSON。
    返回 (data, error_message)；error_message 仅在解析失败时非空。
    """
    text = _strip_json_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"条款打分 JSON 解析失败: {e}"

    if not isinstance(data, dict):
        return None, "条款打分 JSON 根节点必须是对象"

    score_val = data.get("打分")
    if score_val is None:
        score_str = ""
    elif isinstance(score_val, (int, float, bool)):
        score_str = str(score_val)
    else:
        score_str = _coerce_clause_field(score_val)

    out = {
        "本地条款摘录": _coerce_clause_field(data.get("本地条款摘录")),
        "打分": score_str,
        "思考过程": _coerce_clause_field(data.get("思考过程")),
    }
    return out, None


def _build_analysis_clause_query(
    clause_describe: str,
    score_criteria: str,
    other_requirements: str,
) -> str:
    return (
        "【投标文件条款评审】\n"
        f"待评审条款描述：{clause_describe.strip()}\n"
        f"评分规则：{score_criteria.strip()}\n"
        f"其他要求：{other_requirements.strip()}\n\n"
        "请在投标文件中定位与上述条款相关的响应内容，并严格依据评分规则与其他要求给出打分结论与完整思考过程。"
    )


class GetClauseListRequest(BaseModel):
    """获取条款列表请求体"""
    folder_path: str = Field(..., description="文件夹绝对路径（已通过 deal_pdf 处理，含 summary 子目录）")
    task_id: str = Field(..., description="由 verify-model 返回的 taskId")
    base_url: str = Field(..., description="大模型 API 基础地址")
    api_token: str = Field(..., description="API Key")
    model_name: str = Field(..., description="模型名称")


class AnalysisClauseRequest(BaseModel):
    """单条条款对投标文件的打分评审请求体"""
    folder_path: str = Field(..., description="某投标文件 OCR 输出目录绝对路径（含 summary 子目录）")
    clause_describe: str = Field(..., description="条款描述")
    score_criteria: str = Field(..., description="评分规则")
    other_requirements: str = Field("", description="其他要求")
    task_id: str = Field(..., description="由 verify-model 返回的 taskId")
    base_url: str = Field(..., description="大模型 API 基础地址")
    api_token: str = Field(
        ...,
        description="API Key（与 get-clause-list 一致；与 api_key 二选一即可）",
    )
    model_name: str = Field(
        ...,
        description="模型名称（与 get-clause-list 一致；与 model 二选一即可）",
    )


def _run_clause_list_in_background(
    folder: Path,
    task_id: str,
    *,
    base_url: str,
    api_token: str,
    model_name: str,
) -> None:
    """后台调用 up_to_down 获取条款列表，经多轮精炼后通过 WebSocket 单次推送结果"""

    raw_holder: list[str | None] = [None]

    def log_callback(msg: str) -> None:
        asyncio.create_task(
            send_json_to_task(task_id, {"type": "clause_list_log", "message": msg})
        )

    def result_callback(answer: str) -> None:
        raw_holder[0] = answer

    def refine_parse_fail_log(msg: str) -> None:
        asyncio.create_task(
            send_json_to_task(task_id, {"type": "clause_list_log", "message": msg})
        )

    async def _run() -> None:
        try:
            result = await up_to_down(
                folder_path=folder,
                query_content=_CLAUSE_LIST_QUERY,
                output_format="json",
                api_key=api_token,
                base_url=base_url.strip(),
                model=model_name.strip(),
                log_callback=log_callback,
                result_callback=result_callback,
                json_format_instruction=_CLAUSE_LIST_JSON_INSTRUCTION,
            )

            raw = raw_holder[0]
            if raw is None:
                await send_json_to_task(
                    task_id,
                    {"type": "clause_list_result", "data": []},
                )
                await send_json_to_task(
                    task_id,
                    {"type": "clause_list_done", "task_id": task_id, "result": result},
                )
                return

            rows, parse_err = _parse_clause_list_rows(raw)
            if parse_err:
                await send_json_to_task(
                    task_id,
                    {"type": "clause_list_log", "message": parse_err},
                )
                await send_json_to_task(
                    task_id,
                    {"type": "clause_list_result", "data": []},
                )
            elif not rows:
                await send_json_to_task(
                    task_id,
                    {"type": "clause_list_result", "data": []},
                )
            else:
                await send_json_to_task(
                    task_id,
                    {
                        "type": "clause_list_log",
                        "message": "条款列表精炼：第 1 轮（过滤总则类条目）…",
                    },
                )
                client = AsyncOpenAI(
                    api_key=api_token, base_url=base_url.strip()
                )
                model_s = model_name.strip()
                filtered = await refine_clause_list_filter(
                    client,
                    model_s,
                    rows,
                    _parse_clause_list_rows,
                    refine_parse_fail_log,
                )
                with_default = apply_default_scoring(filtered)
                await send_json_to_task(
                    task_id,
                    {
                        "type": "clause_list_log",
                        "message": "条款列表精炼：第 2 轮（字段整理）…",
                    },
                )
                polished = await refine_clause_list_polish(
                    client,
                    model_s,
                    with_default,
                    _parse_clause_list_rows,
                    refine_parse_fail_log,
                )
                refined = apply_default_scoring(polished)
                await send_json_to_task(
                    task_id,
                    {"type": "clause_list_result", "data": refined},
                )

            await send_json_to_task(
                task_id,
                {"type": "clause_list_done", "task_id": task_id, "result": result},
            )
        except Exception as e:
            await send_json_to_task(
                task_id,
                {"type": "error", "message": f"获取条款列表异常: {e}"},
            )

    asyncio.create_task(_run())


def _run_analysis_clause_in_background(
    folder: Path,
    task_id: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    clause_describe: str,
    score_criteria: str,
    other_requirements: str,
) -> None:
    """后台调用 up_to_down 定位原文，再经三角色辩论（支持方→质疑方→仲裁方）评审打分"""

    raw_holder: list[str | None] = [None]
    query_content = _build_analysis_clause_query(
        clause_describe, score_criteria, other_requirements
    )

    def log_callback(msg: str) -> None:
        asyncio.create_task(
            send_json_to_task(task_id, {"type": "analysis_clause_log", "message": msg})
        )

    def result_callback(answer: str) -> None:
        raw_holder[0] = answer

    async def _run() -> None:
        try:
            utd_result = await up_to_down(
                folder_path=folder,
                query_content=query_content,
                output_format="json",
                api_key=api_key,
                base_url=base_url.strip(),
                model=model.strip(),
                log_callback=log_callback,
                result_callback=result_callback,
                json_format_instruction=_ANALYSIS_CLAUSE_JSON_INSTRUCTION,
            )

            raw = raw_holder[0]
            if utd_result != 1 or raw is None:
                await send_json_to_task(
                    task_id,
                    {"type": "analysis_clause_result", "data": None},
                )
                await send_json_to_task(
                    task_id,
                    {
                        "type": "analysis_clause_done",
                        "task_id": task_id,
                        "result": 0,
                    },
                )
                return

            parsed, parse_err = _parse_analysis_clause_result(raw)
            if parse_err:
                await send_json_to_task(
                    task_id,
                    {"type": "analysis_clause_log", "message": parse_err},
                )
                await send_json_to_task(
                    task_id,
                    {"type": "analysis_clause_result", "data": None},
                )
                await send_json_to_task(
                    task_id,
                    {
                        "type": "analysis_clause_done",
                        "task_id": task_id,
                        "result": 0,
                    },
                )
                return

            # ── 三角色辩论评审 ──
            # 使用 up_to_down 提取的原文作为辩论素材
            bid_content = parsed.get("本地条款摘录", "") if parsed else ""
            thinking = parsed.get("思考过程", "") if parsed else ""
            initial_score = parsed.get("打分", "") if parsed else ""

            await send_json_to_task(
                task_id,
                {"type": "analysis_clause_log", "message": "📢 开始三角色辩论评审…"},
            )

            client = AsyncOpenAI(api_key=api_key, base_url=base_url.strip())
            model_s = model.strip()

            # 构造辩论上下文
            debate_context = (
                f"条款描述：{clause_describe}\n"
                f"评分规则：{score_criteria}\n"
                f"其他要求：{other_requirements}\n\n"
                f"投标文件相关内容摘录：\n{bid_content}\n\n"
                f"初步分析思考过程：\n{thinking}"
            )

            # === 1. 支持方 AI ===
            await send_json_to_task(
                task_id,
                {"type": "analysis_clause_log", "message": "✅ 支持方 AI 正在为投标文件辩护…"},
            )

            support_prompt = SUPPORT_PROMPT_V2.format(
                clause_describe=clause_describe,
                score_criteria=score_criteria,
                other_requirements=other_requirements,
                bid_content=bid_content,
                initial_score=initial_score,
                thinking=thinking,
            )

            try:
                support_raw = await _call_llm_debate(client, model_s, support_prompt)
                support_data = _extract_json_safe(support_raw)
                support_score = str(support_data.get("score", initial_score))
                support_reason = str(support_data.get("reason", support_raw))
            except Exception as e:
                support_score = initial_score
                support_reason = f"支持方分析出错，沿用初始评分: {e}"

            await send_json_to_task(
                task_id,
                {
                    "type": "debate_support",
                    "content": support_reason,
                    "data": {"score": support_score, "reason": support_reason},
                },
            )

            # === 2. 质疑方 AI ===
            await send_json_to_task(
                task_id,
                {"type": "analysis_clause_log", "message": "❓ 质疑方 AI 正在审视投标文件…"},
            )

            challenge_prompt = CHALLENGE_PROMPT_V2.format(
                clause_describe=clause_describe,
                score_criteria=score_criteria,
                other_requirements=other_requirements,
                bid_content=bid_content,
                support_score=support_score,
                support_reason=support_reason,
            )

            try:
                challenge_raw = await _call_llm_debate(client, model_s, challenge_prompt)
                challenge_data = _extract_json_safe(challenge_raw)
                challenge_text = str(challenge_data.get("challenge", challenge_raw))
                challenge_score = str(challenge_data.get("suggested_score", support_score))
            except Exception as e:
                challenge_text = f"质疑方分析出错: {e}"
                challenge_score = support_score

            await send_json_to_task(
                task_id,
                {
                    "type": "debate_challenge",
                    "content": challenge_text,
                    "data": {"challenge": challenge_text, "suggested_score": challenge_score},
                },
            )

            # === 3. 仲裁方 AI ===
            await send_json_to_task(
                task_id,
                {"type": "analysis_clause_log", "message": "⚖️ 仲裁方 AI 正在综合判定…"},
            )

            arbitrator_prompt = ARBITRATOR_PROMPT_V2.format(
                clause_describe=clause_describe,
                score_criteria=score_criteria,
                other_requirements=other_requirements,
                bid_content=bid_content,
                support_score=support_score,
                support_reason=support_reason,
                challenge_text=challenge_text,
                challenge_score=challenge_score,
            )

            try:
                arb_raw = await _call_llm_debate(client, model_s, arbitrator_prompt)
                arb_data = _extract_json_safe(arb_raw)
                final_score = str(arb_data.get("score", initial_score))
                final_reason = str(arb_data.get("reason", arb_raw))
                final_excerpt = str(arb_data.get("excerpt", bid_content))
            except Exception as e:
                final_score = initial_score
                final_reason = f"仲裁分析出错，沿用初始评分: {e}"
                final_excerpt = bid_content

            await send_json_to_task(
                task_id,
                {
                    "type": "debate_arbitrator",
                    "content": final_reason,
                    "data": {"score": final_score, "reason": final_reason},
                },
            )

            # 组装最终结果（保持与前端已有的 score_card 结构兼容）
            final_result = {
                "本地条款摘录": final_excerpt,
                "打分": final_score,
                "思考过程": (
                    f"【支持方】{support_reason}\n\n"
                    f"【质疑方】{challenge_text}\n\n"
                    f"【仲裁结论】{final_reason}"
                ),
            }

            await send_json_to_task(
                task_id,
                {"type": "analysis_clause_result", "data": final_result},
            )
            await send_json_to_task(
                task_id,
                {
                    "type": "analysis_clause_done",
                    "task_id": task_id,
                    "result": 1,
                },
            )
        except Exception as e:
            await send_json_to_task(
                task_id,
                {"type": "error", "message": f"条款打分异常: {e}"},
            )
            await send_json_to_task(
                task_id,
                {"type": "analysis_clause_done", "task_id": task_id, "result": 0},
            )

    asyncio.create_task(_run())


@router.post("/get-clause-list")
async def get_clause_list(req: GetClauseListRequest) -> dict:
    """
    获取条款列表接口。

    - 输入（JSON）:
      - folder_path: 文件夹绝对路径（已通过 deal_pdf 处理，含 summary 子目录）
      - task_id: 由 verify-model 返回的 taskId
      - base_url: 大模型 API 基础地址
      - api_token: API 凭证
      - model_name: 模型名称
    - 输出: {"result": 1, "task_id": "..."} 或 {"result": 0, "error": "..."}
    - 后台通过 up_to_down 从已汇总的文件夹中提取评审条款列表
    - 进度和结果通过统一 WebSocket /api/ws/pdf-process/{task_id} 推送

    WebSocket 消息类型:
      - {"type": "clause_list_log", "message": "..."} — 进度日志（含精炼阶段、解析/精炼失败说明）
      - {"type": "clause_list_result", "data": [...]} — 条款列表（**仅在初稿解析成功并完成精炼后推送一次**）；
        data 为对象数组，每项为 {"条款描述": str, "评分标准": str, "其他要求": str}。
        后端会删除分值构成、基准价计算方法、偏差率公式等总则类非条款行；若「评分标准」原文为空则填默认合格制：
        「满足得 100 分，不满足的 0 分」。初稿解析失败时 data 为 []
      - {"type": "clause_list_done", "task_id": "...", "result": 1} — 任务完成
      - {"type": "error", "message": "..."} — 错误
    """
    folder = Path(req.folder_path)
    if not folder.exists() or not folder.is_dir():
        return {"result": 0, "error": "invalid_folder_path"}

    summary_dir = folder / "summary"
    if not summary_dir.exists() or not (summary_dir / "all.txt").exists():
        return {"result": 0, "error": "summary_not_found", "message": "文件夹中未找到 summary/all.txt，请先运行 PDF 处理"}

    if not is_task_registered(req.task_id):
        return {"result": 0, "error": "invalid_task_id"}

    base_url_s = req.base_url.strip()
    if not base_url_s.startswith(("http://", "https://")):
        return {"result": 0, "error": "invalid_base_url"}

    if not req.api_token.strip():
        return {"result": 0, "error": "empty_api_token"}
    if not req.model_name.strip():
        return {"result": 0, "error": "empty_model_name"}

    _run_clause_list_in_background(
        folder,
        req.task_id,
        base_url=base_url_s,
        api_token=req.api_token.strip(),
        model_name=req.model_name.strip(),
    )

    return {"result": 1, "task_id": req.task_id}


@router.post("/analysis-clause")
async def analysis_clause(req: AnalysisClauseRequest) -> dict:
    """
    条款打分接口（针对单个投标文件目录）。

    - 输入（JSON）:
      - folder_path: 投标文件 OCR 输出目录绝对路径（需含 summary/all.txt）
      - clause_describe, score_criteria, other_requirements
      - task_id: verify-model 返回的 taskId（需已建立 WebSocket）
      - base_url: 大模型 Base URL
      - api_token: API Key
      - model_name: 模型名
    - 输出: {"result": 1, "task_id": "..."} 或 {"result": 0, "error": "..."}
    - 进度与结果通过 WebSocket /api/ws/pdf-process/{task_id} 推送

    WebSocket 消息类型:
      - {"type": "analysis_clause_log", "message": "..."} — 进度日志
      - {"type": "analysis_clause_result", "data": {...} | null} — 打分结果；
        data 为 {"本地条款摘录", "打分", "思考过程"}；失败或未产出时为 null
      - {"type": "analysis_clause_done", "task_id": "...", "result": 0|1} — 任务结束
      - {"type": "error", "message": "..."} — 未捕获异常
    """
    folder = Path(req.folder_path)
    if not folder.exists() or not folder.is_dir():
        return {"result": 0, "error": "invalid_folder_path"}

    summary_dir = folder / "summary"
    if not summary_dir.exists() or not (summary_dir / "all.txt").exists():
        return {
            "result": 0,
            "error": "summary_not_found",
            "message": "文件夹中未找到 summary/all.txt，请先运行 PDF 处理",
        }

    if not is_task_registered(req.task_id):
        return {"result": 0, "error": "invalid_task_id"}

    base_url_s = req.base_url.strip()
    if not base_url_s.startswith(("http://", "https://")):
        return {"result": 0, "error": "invalid_base_url"}

    api_key_s = req.api_token.strip()
    model_s = req.model_name.strip()
    if not api_key_s:
        return {
            "result": 0,
            "error": "empty_api_key",
            "message": "请提供 api_token",
        }
    if not model_s:
        return {
            "result": 0,
            "error": "empty_model",
            "message": "请提供 model_name",
        }

    _run_analysis_clause_in_background(
        folder,
        req.task_id,
        base_url=base_url_s,
        api_key=api_key_s,
        model=model_s,
        clause_describe=req.clause_describe,
        score_criteria=req.score_criteria,
        other_requirements=req.other_requirements or "",
    )

    return {"result": 1, "task_id": req.task_id}
