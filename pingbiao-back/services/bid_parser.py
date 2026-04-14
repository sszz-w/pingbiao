"""投标文件解析 + 切片服务"""
import fitz  # PyMuPDF
import os
from models.schemas import Chunk


def parse_bids(files: list[tuple[str, bytes]]) -> dict[str, dict]:
    """
    解析投标 PDF 文件并切片

    Args:
        files: [(file_name, pdf_bytes), ...]

    Returns:
        {bid_id: {"chunks": [Chunk, ...], "file_name": "xxx.pdf"}}
    """
    chunk_size = 800
    overlap = 100
    result = {}

    for file_name, pdf_bytes in files:
        # 提取文本
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        # 生成 bid_id（文件名去扩展名）
        bid_id = os.path.splitext(file_name)[0]

        # 按字符切片
        chunks = []
        start = 0
        index = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            if chunk_text.strip():  # 跳过空白切片
                chunks.append(Chunk(
                    bid_id=bid_id,
                    index=index,
                    content=chunk_text,
                ))
                index += 1
            start += chunk_size - overlap

        result[bid_id] = {
            "chunks": chunks,
            "file_name": file_name,
        }

    return result
