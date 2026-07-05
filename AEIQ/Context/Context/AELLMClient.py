import json
import logging

import httpx

from .AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)

LLM_SERVICE_URL = "http://127.0.0.1:9999/aellms/question"
LLM_HEADERS = {"AE-API-Key": "ae-agent-2024-fixed-key-9527"}

_client: httpx.Client = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(timeout=None, limits=httpx.Limits(max_connections=50))
    return _client


def send_llm_request(payload: AELLMPayload) -> str:
    """同步发送 LLM 请求，复用连接池，返回 LLM 回复文本"""
    try:
        client = _get_client()
        # 打印即将发送的数据（JSON 标准格式输出）
        logger.info(
            "📤 即将发送 LLM 请求:\n%s",
            json.dumps(payload.to_dict(), ensure_ascii=False, indent=2),
        )
        resp = client.post(LLM_SERVICE_URL, json=payload.to_dict(), headers=LLM_HEADERS)
        result = resp.json()
        reply = result.get("response", "")
        logger.info(f"LLM response received, reply_length={len(reply) if reply else 0}")
        return reply
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return ""


def close_client():
    global _client
    if _client and not _client.is_closed:
        _client.close()
        _client = None
