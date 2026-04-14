import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import run
from routers import clause
from routers import verify_model
from routers import upload
from routers import ws
from config import get_base_dir, get_chunk_size, get_chunk_overlap

# 支持命令行参数配置
# 使用方式:
#   python main.py --basedir /path/to/dir --chunk-size 800 --chunk-overlap 100
# 或使用环境变量:
#   export BASEDIR=/path/to/dir
#   export CHUNK_SIZE=800
#   export CHUNK_OVERLAP=100
#   python main.py

def parse_args():
    """解析命令行参数"""
    args = {}
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--basedir" and i + 1 < len(sys.argv) - 1:
            args["basedir"] = sys.argv[i + 2]
        elif arg == "--chunk-size" and i + 1 < len(sys.argv) - 1:
            args["chunk_size"] = sys.argv[i + 2]
        elif arg == "--chunk-overlap" and i + 1 < len(sys.argv) - 1:
            args["chunk_overlap"] = sys.argv[i + 2]
    return args

# 解析命令行参数并设置环境变量
cmd_args = parse_args()
if cmd_args.get("basedir"):
    os.environ["BASEDIR"] = cmd_args["basedir"]
if cmd_args.get("chunk_size"):
    os.environ["CHUNK_SIZE"] = cmd_args["chunk_size"]
if cmd_args.get("chunk_overlap"):
    os.environ["CHUNK_OVERLAP"] = cmd_args["chunk_overlap"]

# 打印当前配置
# 打印当前配置
print(f"[Config] Project settings:")
print(f"  Base Directory: {get_base_dir()}")
print(f"  Chunk Size: {get_chunk_size()}")
print(f"  Chunk Overlap: {get_chunk_overlap()}")
print()

app = FastAPI(title="Pingbiao-Power Backend")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(run.router, prefix="/api")
app.include_router(clause.router, prefix="/api")
app.include_router(verify_model.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(ws.router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "Pingbiao-Power Backend API"}
