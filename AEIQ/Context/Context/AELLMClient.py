import json
import logging

import httpx

from .AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)

LLM_SERVICE_URL = "http://127.0.0.1:9999/aellms/question"
LLM_HEADERS = {"AE-API-Key": "ae-agent-2024-fixed-key-9527"}

# AsyncClient 绑定到首次创建它的 loop（AEUserContext 的持久 loop），跨请求复用连接池
_async_client: httpx.AsyncClient = None


def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=50))
    return _async_client


async def send_llm_request(payload: AELLMPayload) -> str:
    """异步发送 LLM 请求（须在事件循环内调用），复用连接池，返回 LLM 回复文本"""
    try:
        client = _get_async_client()
        # 打印即将发送的数据（JSON 标准格式输出）
        logger.info(
            "📤 即将发送 LLM 请求:\n%s",
            json.dumps(payload.to_llm_request_dic(), ensure_ascii=False, indent=2),
        )
        resp = await client.post(LLM_SERVICE_URL, json=payload.to_llm_request_dic(), headers=LLM_HEADERS)
        result = resp.json()
        reply = result.get("response", "")
        logger.info(f"LLM response received, reply_length={len(reply) if reply else 0}")
        return reply
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return ""


async def close_client():
    global _async_client
    if _async_client and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None
