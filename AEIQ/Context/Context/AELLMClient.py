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


async def send_llm_request(payload: AELLMPayload) -> dict:
    """两步流程：仅把内容模板发给 LLM 生成内容，回包后回填固定信封，返回完整信封 dict（含可信 ident）。

    LLM 全程不接触 ident 等路由字段，故不会腐蚀路由信封；ident 由框架持有的信封逐字保留。
    失败时返回 None，由调用方跳过 dispatch。
    """
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
        filled_content = _parse_content_json(reply)
        if filled_content is None:
            logger.error("LLM 内容解析失败，丢弃回包")
            return None
        envelope = payload.fill_content(filled_content)
        logger.info("LLM 回填信封:\n%s", json.dumps(envelope, ensure_ascii=False, indent=2, default=str))
        return envelope
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return None


def _strip_code_fence(text: str) -> str:
    """去掉 LLM 回复可能包裹的 ```json ... ``` 代码块围栏。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


def _parse_content_json(reply: str):
    """解析 LLM 回包为填充内容（dict / list）；失败返回 None。"""
    if not reply:
        return None
    stripped = _strip_code_fence(reply)
    try:
        return json.loads(stripped)
    except (ValueError, TypeError) as e:
        logger.error("内容 JSON 解析失败: %s\nreply(前2000字符)=%s", e, reply[:2000])
        return None


async def close_client():
    global _async_client
    if _async_client and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None
