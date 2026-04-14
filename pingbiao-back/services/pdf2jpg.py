"""将 PDF 每一页转换为 JPG 图片"""
import uuid
from pathlib import Path

import fitz  # PyMuPDF


def pdf_to_jpg(save_dir: str | Path, pdf_path: str | Path) -> Path:
    """
    将 PDF 文件每一页转成 JPG 图片。

    Args:
        save_dir: 保存的根文件夹 A
        pdf_path: PDF 文件路径 B

    Returns:
        生成图片所在文件夹的绝对路径（A/C 的 resolve 结果）

    生成的图片以页码命名（1.jpg, 2.jpg, ...），保存在 A/C 下，
    其中 C = B 的文件名（不含扩展名）+ UUID。
    """
    save_dir = Path(save_dir)
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    # C 的文件夹名 = B 的文件名（不含扩展名）+ UUID
    pdf_stem = pdf_path.stem
    folder_c_name = f"{pdf_stem}_{uuid.uuid4().hex}"
    folder_c = save_dir / folder_c_name

    folder_c.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            # alpha=False：JPEG 不支持透明通道
            pix = page.get_pixmap(alpha=False)
            out_path = folder_c / f"{i + 1}.jpg"
            pix.save(str(out_path), jpg_quality=50)
    finally:
        doc.close()

    return folder_c.resolve()

if __name__ == '__main__':
    print(pdf_to_jpg(".", "/Users/yuzhe/Desktop/演示数据/浙xx柜电气有限公司投标文件.pdf"))