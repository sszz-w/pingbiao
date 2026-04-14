"""
验证大模型是否可用
输入: base_url, api_token, model_name
输出: 0 表示连接失败, 1 表示连接成功
"""
import asyncio
from openai import AsyncOpenAI


async def verify_model(base_url: str, api_token: str, model_name: str) -> int:
    """
    验证大模型 API 是否可用。

    Args:
        base_url: API 基础地址（如 https://api.openai.com/v1）
        api_token: API 密钥
        model_name: 模型名称（如 gpt-4o、deepseek-chat）

    Returns:
        1: 连接成功
        0: 连接失败
    """
    try:
        client = AsyncOpenAI(api_key=api_token, base_url=base_url)
        # 发送最小化请求验证连接
        response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "hi"}],  # type: ignore
            max_tokens=5,
        )
        return 1
    except Exception:
        return 0
