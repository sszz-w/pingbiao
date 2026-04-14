"""项目全局配置"""
import os
from pathlib import Path

# 基础目录 - 用于保存生成的文件（如 JPG 图片、报告等）
# 可通过环境变量 BASEDIR 设置，默认为项目根目录
BASE_DIR = Path(os.getenv("BASEDIR", "."))

# 切片大小 - PDF 文本切成多少字符一个切片
# 可通过环境变量 CHUNK_SIZE 设置，默认为 10
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 10))

# 切片重叠 - 相邻切片的重叠字符数
# 可通过环境变量 CHUNK_OVERLAP 设置，默认为 2
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 2))

# 检索的最相关切片数量
TOP_K = int(os.getenv("TOP_K", 5))

# down_to_up 专用：每组文件数、重叠文件数（与 bid_parser 的字符切片语义不同）
DOWN_TO_UP_CHUNK_SIZE = int(os.getenv("DOWN_TO_UP_CHUNK_SIZE", "10"))
DOWN_TO_UP_CHUNK_OVERLAP = int(os.getenv("DOWN_TO_UP_CHUNK_OVERLAP", "1"))


def get_base_dir() -> Path:
    """获取基础目录，自动创建如果不存在"""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    return BASE_DIR


def get_chunk_size() -> int:
    """获取切片大小"""
    return CHUNK_SIZE


def get_chunk_overlap() -> int:
    """获取切片重叠大小"""
    return CHUNK_OVERLAP


def get_top_k() -> int:
    """获取检索数量"""
    return TOP_K


def get_down_to_up_chunk_size() -> int:
    """获取 down_to_up 每组文件数"""
    return DOWN_TO_UP_CHUNK_SIZE


def get_down_to_up_chunk_overlap() -> int:
    """获取 down_to_up 重叠文件数"""
    return DOWN_TO_UP_CHUNK_OVERLAP

