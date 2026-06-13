import asyncio
import logging
from typing import Callable, Any

import httpx

from .AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)

LLM_SERVICE_URL = "http://127.0.0.1:9999/aellms/question"
LLM_HEADERS = {"AE-API-Key": "ae-agent-2024-fixed-key-9527"}

_client: httpx.AsyncClient = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=50))
    return _client


async def send_llm_request(payload: AELLMPayload, callback: Callable[[str], Any]) -> None:
    """异步发送 LLM 请求，支持并发复用连接池"""
    try:
        client = _get_client()
        resp = await client.post(LLM_SERVICE_URL, json=payload.to_dict(), headers=LLM_HEADERS)
        result = resp.json()
        reply = result.get("response", "")
        await callback(reply) if asyncio.iscoroutinefunction(callback) else callback(reply)
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        await callback("") if asyncio.iscoroutinefunction(callback) else callback("")


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
