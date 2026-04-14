"""
模型验证接口路由
POST /api/verify-model - 验证大模型是否可用
"""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.verify_model import verify_model
from services.ws_manager import register_task

router = APIRouter()


class VerifyModelRequest(BaseModel):
    """验证模型请求体"""
    base_url: str = Field(..., description="API 基础地址，如 https://api.openai.com/v1")
    api_token: str = Field(..., description="API 密钥")
    model_name: str = Field(..., description="模型名称，如 gpt-4o、deepseek-chat")

    class Config:
        json_schema_extra = {
            "example": {
                "base_url": "https://api.openai.com/v1",
                "api_token": "sk-xxx",
                "model_name": "gpt-4o"
            }
        }


class VerifyModelResponse(BaseModel):
    """验证模型响应体"""
    status: str = Field(..., description="状态：success 或 failed")
    available: bool = Field(..., description="模型是否可用")
    code: int = Field(..., description="返回码：1 表示可用，0 表示不可用")
    message: str = Field(..., description="详细信息")
    taskId: str | None = Field(None, description="验证成功时的会话 ID，用于建立 WebSocket；失败时为 null")


@router.post("/verify-model", response_model=VerifyModelResponse)
async def verify_model_endpoint(request: VerifyModelRequest) -> VerifyModelResponse:
    """
    验证大模型 API 是否可用
    
    该接口会向指定的 LLM API 发送一个最小化请求，用于验证 API 是否可用。
    
    **参数说明：**
    - base_url: API 的基础地址
      - OpenAI: https://api.openai.com/v1
      - DeepSeek: https://api.deepseek.com/v1
      - 阿里云 Qwen: https://coding.dashscope.aliyuncs.com/v1
    - api_token: API 密钥
    - model_name: 模型名称
      - OpenAI: gpt-4o, gpt-4-turbo, gpt-3.5-turbo
      - DeepSeek: deepseek-chat
      - 阿里云: qwen3.5-plus, qwen-max
    
    **返回值说明：**
    - status: success (可用) 或 failed (不可用)
    - available: true/false
    - code: 1 (可用) 或 0 (不可用)
    - message: 详细信息
    
    **示例请求：**
    ```json
    {
        "base_url": "https://api.openai.com/v1",
        "api_token": "sk-xxx",
        "model_name": "gpt-4o"
    }
    ```
    
    **示例响应（成功）：**
    ```json
    {
        "status": "success",
        "available": true,
        "code": 1,
        "message": "模型可用",
        "taskId": "a1b2c3d4..."
    }
    ```
    成功时返回 taskId，前端需连接 ws://host/api/ws/pdf-process/{taskId} 建立统一 WebSocket，供后续接口复用。

    **示例响应（失败）：**
    ```json
    {
        "status": "failed",
        "available": false,
        "code": 0,
        "message": "连接失败：Invalid API key",
        "taskId": null
    }
    ```
    """
    try:
        result = await verify_model(
            base_url=request.base_url,
            api_token=request.api_token,
            model_name=request.model_name
        )

        if result == 1:
            task_id = uuid.uuid4().hex
            register_task(task_id)
            return VerifyModelResponse(
                status="success",
                available=True,
                code=1,
                message="大模型可用",
                taskId=task_id,
            )
        else:
            return VerifyModelResponse(
                status="failed",
                available=False,
                code=0,
                message="大模型连接失败",
                taskId=None,
            )
    except Exception as e:
        return VerifyModelResponse(
            status="failed",
            available=False,
            code=0,
            message=f"大模型连接失败：{str(e)}",
            taskId=None,
        )
