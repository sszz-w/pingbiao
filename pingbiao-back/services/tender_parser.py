"""招标文件解析服务"""
import fitz  # PyMuPDF
import json
from openai import AsyncOpenAI
from models.schemas import Clause
from prompts.templates import TENDER_PARSE_PROMPT


async def parse_tender(
    pdf_bytes: bytes,
    client: AsyncOpenAI,
    model: str
) -> list[Clause]:
    """
    解析招标 PDF，提取评审条款

    Args:
        pdf_bytes: PDF 文件字节流
        client: OpenAI 客户端
        model: 模型名称

    Returns:
        条款列表
    """
    # 1. 使用 PyMuPDF 提取文本
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_content = ""
    for page in doc:
        text_content += page.get_text()
    doc.close()

    # 2. 使用 LLM 提取条款
    prompt = TENDER_PARSE_PROMPT.format(content=text_content[:8000])  # 限制长度避免超 token

    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    result_text = response.choices[0].message.content.strip()

    # 3. 解析 JSON 并构造 Clause 对象
    try:
        clauses_data = json.loads(result_text)
        clauses = []
        for i, item in enumerate(clauses_data):
            clauses.append(Clause(
                id=str(i + 1),
                no=item["no"],
                desc=item["desc"],
                score=float(item["score"]),
                weight=float(item.get("weight", 1.0)),
                order=i + 1
            ))
        return clauses
    except Exception as e:
        # 解析失败时返回空列表
        print(f"招标文件解析失败: {e}")
        return []
