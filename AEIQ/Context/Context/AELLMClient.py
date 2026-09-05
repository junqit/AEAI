import json
import logging

import httpx
from json_repair import repair_json

from .AELLMPayload import AELLMPayload
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT

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
    LLM 返回错误或内容不可解析时，不再丢弃回包，而是把原数据结构内 AE_CONTENT 置为
    "llm 生成失败" 后返回完整信封，使 flow 仍能收到回包事件并推进，避免挂死。
    """
    try:
        client = _get_async_client()
        # 诊断：即将发送的 LLM 请求（messages + 内容模板），看清上游摘要是否空洞
        logger.info(
            "📤 即将发送 LLM 请求:\n%s",
            json.dumps(payload.to_llm_request_dic(), ensure_ascii=False, indent=2),
        )
        resp = await client.post(LLM_SERVICE_URL, json=payload.to_llm_request_dic(), headers=LLM_HEADERS)
        result = resp.json()
        reply = result.get("response", "")
        elapsed = result.get("elapsed_seconds")
        logger.info(
            "[LLM] 收到回复: %d chars%s",
            len(reply) if reply else 0,
            f", 耗时: {elapsed:.2f}s" if isinstance(elapsed, (int, float)) else "",
        )
        # 诊断：原始回复预览，确认 LLM 究竟回了什么（content 是否为空 / 内容是否落在别的字段）
        logger.info("[LLM] 原始回复预览(前800字符): %s", (reply or "")[:800])
        # token 消耗：依赖网关透传上游 usage（prompt_tokens / completion_tokens / total_tokens）
        usage = result.get("usage") or {}
        if not usage:
            usage = {k: result[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens") if k in result}
        if usage:
            logger.info(
                "[LLM] token 消耗: prompt=%s, completion=%s, total=%s",
                usage.get("prompt_tokens", "-"),
                usage.get("completion_tokens", "-"),
                usage.get("total_tokens", "-"),
            )
        filled_content = _parse_content_json(reply)
        # 诊断：解析后内容预览，确认 content 占位符被填成了什么（是否为空串）
        logger.info("[LLM] 解析内容预览(前800字符): %s", str(filled_content)[:800])
        if filled_content is None:
            logger.error("LLM 内容解析失败，回填失败占位信封")
            return _build_failure_envelope(payload)
        envelope = payload.fill_content(filled_content)
        # 诊断：回填后的完整信封（含 AE_CONTENT），确认最终内容是否为空
        logger.info("LLM 回填信封:\n%s", json.dumps(envelope, ensure_ascii=False, indent=2, default=str))
        return envelope
    except Exception as e:
        logger.error(f"LLM request failed: {e}，回填失败占位信封")
        return _build_failure_envelope(payload)


def _build_failure_envelope(payload: AELLMPayload, reason: str = "") -> dict:
    """LLM 失败 / 不可解析时，把原数据结构内 AE_CONTENT 置为失败原因，返回完整信封。

    复用 payload.fill_content 的回填逻辑：最内层含 AE_CONTENT 的 dict 直接替换其值；
    否则用 {AE_CONTENT: reason} 整体替换最内层 llm_out。两种情况均保证信封内出现
    AE_CONTENT=失败原因，下游 flow 可据此收尾推进。
    """
    return payload.fill_content({AE_CONTENT: reason})


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
    """解析 LLM 回包为填充内容（dict / list）；失败返回 None。

    用 json_repair 容错解析：LLM 常产出字符串值内裸换行、非法转义（如正则 \\d）、
    尾逗号等不合规 JSON，json_repair 可修复后直接返回解析对象，避免解析失败回填
    空信封导致下游 flow 拿到空结果。
    """
    if not reply:
        return None
    stripped = _strip_code_fence(reply)
    try:
        return repair_json(stripped, return_objects=True)
    except Exception as e:
        logger.error("内容 JSON 解析失败: %s\nreply(前2000字符)=%s", e, reply[:2000])
        return None


async def close_client():
    global _async_client
    if _async_client and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None
