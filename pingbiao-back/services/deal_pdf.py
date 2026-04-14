"""对文件夹中的 JPG 图片进行 OCR 识别，并将结果保存为同名 txt 文件"""
import asyncio
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rapidocr_onnxruntime import RapidOCR

from config import get_base_dir
from services.down_to_up import down_to_up
from services.pdf2jpg import pdf_to_jpg
from services.ws_manager import send_json_to_task, is_task_registered


def _log(msg: str, log_cb: Callable[[str], None] | None) -> None:
    """输出日志：有回调则用回调，否则 print"""
    if log_cb:
        log_cb(msg)
    else:
        print(msg, flush=True)


async def ocr_folder(
    folder_path: str | Path,
    log_callback: Callable[[str], None] | None = None,
    pdf_name: str | None = None,
) -> int:
    """
    对文件夹 A 中所有 jpg 图片进行 OCR 识别，并把 OCR 结果保存到同一文件夹中。
    每个图片的识别结果保存到 txt 中，命名与图片相同（如 1.jpg -> 1.txt）。

    Args:
        folder_path: 包含 jpg 图片的文件夹路径
        log_callback: 日志回调函数
        pdf_name: PDF 文件名（用于进度显示）

    Returns:
        成功处理的图片数量
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"文件夹不存在: {folder}")

    if not folder.is_dir():
        raise NotADirectoryError(f"路径不是文件夹: {folder}")

    # 支持的 jpg, png 扩展名
    jpg_extensions = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG"}
    jpg_files = [f for f in folder.iterdir() if f.is_file() and f.suffix in jpg_extensions]
    
    if not jpg_files:
        _log("⚠️  文件夹中没有找到文件", log_callback)
        return 0

    _log(f"📊 找到 {len(jpg_files)} 个文件页码", log_callback)

    def _natural_sort_key(p: Path):
        """按文件名中的数字自然排序，如 1.jpg, 2.jpg, 10.jpg"""
        parts = re.split(r"(\d+)", p.stem)
        return [int(x) if x.isdigit() else x.lower() for x in parts if x]

    sorted_files = sorted(jpg_files, key=_natural_sort_key)
    engine = RapidOCR(det_limit_side_len=640, is_concat=True, use_angle_cls=False)
    loop = asyncio.get_running_loop()

    # 记录 OCR 开始时间
    start_time = time.time()

    # 使用 pdf_name 或默认文件夹名
    display_name = pdf_name or folder.name
    parts = display_name.split(".pdf", 1)
    result_name = parts[0] + ".pdf" if len(parts) > 1 else display_name

    async def _process_one(idx: int, img_path: Path, executor: ThreadPoolExecutor) -> bool:
        result, elapse = await loop.run_in_executor(executor, engine, img_path)
        text_lines = [line[1] for line in result] if result else []
        txt_path = img_path.with_suffix(".txt")
        text_content = "\n".join(text_lines).strip()
        await asyncio.to_thread(txt_path.write_text, text_content, encoding="utf-8")

        # 计算进度百分比和累计耗时
        progress_percent = int((idx / len(sorted_files)) * 100)
        elapsed_time = time.time() - start_time

        # 格式化时间显示
        if elapsed_time < 60:
            time_str = f"{elapsed_time:.1f}秒"
        else:
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            time_str = f"{minutes}分{seconds}秒"

        # 新格式: 解析招标文件 xxx 进度：**%（时间）
        _log(f"解析招标文件 {result_name} 中：已用时{time_str}，处理完第{idx}页", log_callback)
        return True

    _log("🔄 开始异步处理图片（线程池=10，有空闲则排队进入）...\n", log_callback)

    with ThreadPoolExecutor(max_workers=10) as ocr_executor:
        tasks = [_process_one(idx, p, ocr_executor) for idx, p in enumerate(sorted_files, 1)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    count = 0
    for img_path, r in zip(sorted_files, results):
        if isinstance(r, Exception):
            _log(f"❌ {img_path.name}: {r}", log_callback)
            raise RuntimeError(f"视图理解 处理失败 {img_path.name}: {r}") from r
        count += 1

    return count


async def deal_pdf(
    pdf_path: str | Path,
    save_dir: str | Path | None = None,
    log_callback: Callable[[str], None] | None = None,
    *,
    task_id: str | None = None,
    pdf_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> int:
    """
    异步处理 PDF：先转 JPG 图片，再对图片做 OCR，最后调用 LLM 从下往上汇总。

    Args:
        pdf_path: PDF 文件路径
        save_dir: 保存根目录，默认使用 config.get_base_dir()
        log_callback: 可选，用于实时输出日志（如 WebSocket 推送）
        task_id: 可选，WebSocket 连接标识，用于实时推送日志到前端
        pdf_name: 可选，原始 PDF 文件名（用于 ocr_done 消息），默认取 pdf_path 的文件名
        api_key, base_url, model: 大模型配置（由 /upload-pdf 传入）

    Returns:
        1: 上传/处理成功
        0: 上传/处理失败
    """
    save_dir = Path(save_dir) if save_dir is not None else get_base_dir()
    pdf_path = Path(pdf_path)

    try:
        if base_url and model:
            masked = f"{api_key[:4]}...***" if api_key and len(api_key) > 4 else ("***" if api_key else "(无)")
            _log(f"🤖 已接收 LLM 配置: base_url={base_url}, model={model}, api_token={masked}", log_callback)
        _log("📄 开始对 PDF 转视图理解...", log_callback)
        folder_c = await asyncio.to_thread(pdf_to_jpg, save_dir, pdf_path)
        _log(f"✅ PDF 转视图完成，输出目录: {folder_c}，接下来逐页进行理解\n", log_callback)

        # 传入 pdf_name 用于进度显示
        display_pdf_name = pdf_name or Path(pdf_path).name
        await ocr_folder(folder_c, log_callback, pdf_name=display_pdf_name)
        _log("✅ 视图理解 处理完成", log_callback)

        # 通过 WebSocket 返回 OCR 结果的父目录绝对路径
        if task_id:
            ocr_parent_dir = str(Path(folder_c).resolve())
            await send_json_to_task(task_id, {
                "type": "ocr_done",
                "pdf_name": pdf_name or Path(pdf_path).name,
                "parent_dir": ocr_parent_dir,
            })

        # OCR 完成后，调用 LLM 从下往上汇总
        if api_key and base_url and model:
            _log("📝 开始从下往上 大模型理解全文 汇总...", log_callback)
            summary_result = await down_to_up(
                folder_path=folder_c,
                api_key=api_key,
                base_url=base_url,
                model=model,
                task_id=task_id,
                log_callback=log_callback,
            )
            if summary_result == 0:
                _log("❌ 大模型理解全文 汇总失败", log_callback)
                return 0
            _log("✅ 大模型理解全文 汇总完成", log_callback)

            # 汇总完成后，自动调用条款列表抽取
            if task_id and is_task_registered(task_id):
                _log("📋 开始自动抽取条款列表...", log_callback)
                # 导入条款列表抽取函数
                from routers.clause import _run_clause_list_in_background

                # 调用条款列表抽取（后台异步执行）
                _run_clause_list_in_background(
                    Path(folder_c),
                    task_id,
                    base_url=base_url,
                    api_token=api_key,
                    model_name=model,
                )
                _log("✅ 条款列表抽取任务已启动（后台执行）", log_callback)
        else:
            _log("⚠️ 未配置 大模型 参数，跳过从下往上汇总", log_callback)

        _log("✅ 全部处理完成", log_callback)
        return 1
    except Exception as e:
        _log(f"❌ 处理失败: {e}", log_callback)
        return 0


async def deal_pdf2(
    pdf_path: str | Path,
    save_dir: str | Path | None = None,
    log_callback: Callable[[str], None] | None = None,
    *,
    task_id: str | None = None,
    pdf_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> tuple[int, str | None]:
    """
    异步处理 PDF：先转 JPG 图片，再对图片做 OCR，最后调用 LLM 从下往上汇总。

    Args:
        pdf_path: PDF 文件路径
        save_dir: 保存根目录，默认使用 config.get_base_dir()
        log_callback: 可选，用于实时输出日志（如 WebSocket 推送）
        task_id: 可选，WebSocket 连接标识，用于实时推送日志到前端
        pdf_name: 可选，原始 PDF 文件名（用于 ocr_done 消息），默认取 pdf_path 的文件名
        api_key, base_url, model: 大模型配置（由 /upload-pdf 传入）

    Returns:
        (1, parent_dir): 处理成功，parent_dir 为 OCR 输出目录绝对路径
        (0, None): 处理失败
    """
    save_dir = Path(save_dir) if save_dir is not None else get_base_dir()
    pdf_path = Path(pdf_path)

    try:
        if base_url and model:
            masked = f"{api_key[:4]}...***" if api_key and len(api_key) > 4 else ("***" if api_key else "(无)")
            _log(f"🤖 已接收 LLM 配置: base_url={base_url}, model={model}, api_token={masked}", log_callback)
        _log("📄 开始对 PDF 转视图理解...", log_callback)
        folder_c = await asyncio.to_thread(pdf_to_jpg, save_dir, pdf_path)
        _log(f"✅ PDF 转视图完成，输出目录: {folder_c}，接下来逐页进行理解\n", log_callback)

        # 传入 pdf_name 用于进度显示
        display_pdf_name = pdf_name or Path(pdf_path).name
        await ocr_folder(folder_c, log_callback, pdf_name=display_pdf_name)
        _log("✅ 视图理解 处理完成", log_callback)

        # 通过 WebSocket 返回 OCR 结果的父目录绝对路径
        if task_id:
            ocr_parent_dir = str(Path(folder_c).resolve())
            await send_json_to_task(task_id, {
                "type": "ocr_done",
                "pdf_name": pdf_name or Path(pdf_path).name,
                "parent_dir": ocr_parent_dir,
            })

        # OCR 完成后，调用 LLM 从下往上汇总
        if api_key and base_url and model:
            _log("📝 开始从下往上 大模型理解全文 汇总...", log_callback)
            summary_result = await down_to_up(
                folder_path=folder_c,
                api_key=api_key,
                base_url=base_url,
                model=model,
                task_id=task_id,
                log_callback=log_callback,
            )
            if summary_result == 0:
                _log("❌ 大模型理解全文 汇总失败", log_callback)
                return 0, None
            _log("✅ 大模型理解全文 汇总完成", log_callback)
        else:
            _log("⚠️ 未配置 大模型 参数，跳过从下往上汇总", log_callback)

        _log("✅ 全部处理完成", log_callback)
        return 1, str(Path(folder_c).resolve())
    except Exception as e:
        _log(f"❌ 处理失败: {e}", log_callback)
        return 0, None