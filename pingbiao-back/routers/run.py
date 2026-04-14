from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
import json
from openai import AsyncOpenAI

from services.tender_parser import parse_tender
from services.bid_parser import parse_bids
from services.retriever import retrieve_chunks
from services.debate import debate_and_score
from services.report import generate_report

router = APIRouter()


@router.post("/run")
async def run_evaluation(
    tender_file: UploadFile = File(...),
    bid_files: List[UploadFile] = File(...),
    api_base: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
):
    """
    主评标接口
    - 接收招标文件（单个 PDF）和投标文件（多个 PDF）
    - 返回 NDJSON 流式响应
    """
    # 文件格式校验
    if not tender_file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="招标文件必须是 PDF 格式")

    for bid_file in bid_files:
        if not bid_file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"投标文件 {bid_file.filename} 必须是 PDF 格式")

    # 初始化 OpenAI 客户端
    client = AsyncOpenAI(api_key=api_key, base_url=api_base)

    # 返回 NDJSON 流
    async def event_stream():
        try:
            # === Step 1: 解析招标文件 ===
            yield json.dumps({
                "type": "progress_update",
                "stage": "pdf_parse",
                "current": 0,
                "total": 1 + len(bid_files),
                "message": f"正在解析招标文件 {tender_file.filename}..."
            }, ensure_ascii=False) + "\n"

            tender_bytes = await tender_file.read()
            clauses = await parse_tender(tender_bytes, client, model)

            yield json.dumps({
                "type": "parse_tender_done",
                "clauses": [c.model_dump() for c in clauses]
            }, ensure_ascii=False) + "\n"

            # === Step 2: 解析投标文件 ===
            bid_files_data = []
            for idx, bf in enumerate(bid_files):
                yield json.dumps({
                    "type": "progress_update",
                    "stage": "pdf_parse",
                    "current": idx + 1,
                    "total": 1 + len(bid_files),
                    "message": f"正在解析投标文件 {bf.filename}..."
                }, ensure_ascii=False) + "\n"

                bid_files_data.append((bf.filename, await bf.read()))

            bids = parse_bids(bid_files_data)

            for bid_id, data in bids.items():
                yield json.dumps({
                    "type": "parse_bid_done",
                    "bid_id": bid_id,
                    "file_name": data["file_name"]
                }, ensure_ascii=False) + "\n"

            # === Step 3: 逐条款 × 逐投标评审 ===
            results = []
            total_tasks = len(clauses) * len(bids)
            current_task = 0

            for clause in clauses:
                for bid_id, data in bids.items():
                    current_task += 1
                    yield json.dumps({
                        "type": "progress_update",
                        "stage": "debate",
                        "current": current_task,
                        "total": total_tasks,
                        "message": f"正在评审条款 {clause.no} × {data['file_name']}..."
                    }, ensure_ascii=False) + "\n"
                    bid_name = data["file_name"]
                    chunks = data["chunks"]

                    # 发送 clause_start 事件
                    yield json.dumps({
                        "type": "clause_start",
                        "clause": clause.model_dump(),
                        "bid_name": bid_name
                    }, ensure_ascii=False) + "\n"

                    # 检索相关切片
                    relevant_chunks = retrieve_chunks(clause.desc, chunks, top_k=5)

                    # AI 辩论打分
                    final_score = None
                    final_reason = None

                    async for event in debate_and_score(client, model, clause, relevant_chunks):
                        # 发送辩论事件
                        if event.type == "debate":
                            yield json.dumps({
                                "type": "debate",
                                "role": event.role,
                                "content": event.content
                            }, ensure_ascii=False) + "\n"
                        elif event.type == "score":
                            final_score = event.score
                            final_reason = event.reason

                    # 发送 score 事件
                    if final_score is not None:
                        yield json.dumps({
                            "type": "score",
                            "clause_no": clause.no,
                            "bid_name": bid_name,
                            "score": final_score,
                            "reason": final_reason
                        }, ensure_ascii=False) + "\n"

                        results.append({
                            "clause_no": clause.no,
                            "bid_name": bid_name,
                            "score": final_score,
                            "reason": final_reason
                        })

                    # 发送 clause_end 事件
                    yield json.dumps({
                        "type": "clause_end"
                    }, ensure_ascii=False) + "\n"

            # === Step 4: 生成报告 ===
            yield json.dumps({
                "type": "progress_update",
                "stage": "report",
                "current": 0,
                "total": 1,
                "message": "正在生成评标报告..."
            }, ensure_ascii=False) + "\n"

            html_report = generate_report(clauses, bids, results)

            yield json.dumps({
                "type": "report",
                "html": html_report
            }, ensure_ascii=False) + "\n"

        except Exception as e:
            yield json.dumps({
                "type": "error",
                "error": type(e).__name__,
                "message": str(e)
            }, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson"
    )
