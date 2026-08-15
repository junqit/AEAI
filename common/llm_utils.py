"""
LLM 消息处理工具（共享）

供 llms 服务各模型在构造网关请求时复用。
"""
from typing import List, Dict, Any, Tuple, Callable
import logging

# 视为系统提示的角色：
# - "system"：标准系统角色
# - "context"：AEIQ 中用于承载上下文/角色信息（工作目录、role prompt 等）
SYSTEM_ROLES = {"system", "context"}

# Anthropic message 结构字段键与取值（不可变常量）
_KEY_CONTENT = "content"
_KEY_TYPE = "type"
_KEY_TEXT = "text"
_VAL_TEXT_BLOCK = "text"


def split_system_messages(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    从 messages 中分离 system/context 角色内容，合并为顶层 system 文本；
    其余消息按原序返回。

    用于 Anthropic 兼容网关：system 作为顶层字段下发，messages 仅保留对话消息，
    避免出现连续多条 user 消息。

    Args:
        messages: 原始消息列表，可能含 system/context 角色

    Returns:
        (system_text, chat_messages): 合并后的 system 文本（无则为空串）与对话消息列表
    """
    system_parts: List[str] = []
    chat: List[Dict[str, Any]] = []
    for m in messages:
        if m.get("role") in SYSTEM_ROLES:
            c = m.get("content", "")
            if c:
                system_parts.append(c if isinstance(c, str) else str(c))
        else:
            chat.append(m)
    return "\n\n".join(system_parts), chat


def extract_message_text(result: Any) -> str:
    """
    从 Anthropic 兼容的 message 响应中提取全部 text 块文本并拼接。

    用于进度回调：在非流式调用拿到完整结果后，统计「生成累计长度」。

    Args:
        result: API 响应（dict，含 content 块数组）

    Returns:
        str: 所有 type==text 的 content 块文本拼接结果；非预期结构返回空串
    """
    if not isinstance(result, dict):
        return ""
    content = result.get(_KEY_CONTENT)
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict) and block.get(_KEY_TYPE) == _VAL_TEXT_BLOCK:
            parts.append(block.get(_KEY_TEXT, ""))
    return "".join(parts)


def make_progress_info(content: str, max_tokens: int, final: bool) -> Dict[str, Any]:
    """
    构造统一的进度回调信息。

    整体进度 = 生成累计长度 / max_tokens（输出预算即本次可用的上下文空间），
    clamp 到 [0, 1]。

    Args:
        content: 当前累计/最终生成内容
        max_tokens: 输出预算（上下文空间）
        final: 是否为最终结果（流式逐 delta 为 False，结束/非流式为 True）

    Returns:
        dict: progress / content / generated_length / max_tokens / remaining / final
    """
    generated_length = len(content)
    progress = (generated_length / max_tokens) if max_tokens and max_tokens > 0 else 0.0
    if progress > 1.0:
        progress = 1.0
    return {
        "progress": progress,
        "content": content,
        "generated_length": generated_length,
        "max_tokens": max_tokens,
        "remaining": max(0, max_tokens - generated_length),
        "final": final,
    }


def fire_progress(
    callback: Callable[[Dict[str, Any]], None],
    content: str,
    max_tokens: int,
    final: bool,
) -> None:
    """
    安全地触发进度回调：构造信息并调用；回调自身的异常被捕获并告警，
    绝不影响主生成流程。callback 为 None 时直接返回。
    """
    if callback is None:
        return
    try:
        callback(make_progress_info(content, max_tokens, final))
    except Exception as cb_err:
        logging.getLogger(__name__).warning(
            "⚠️ progress_callback 执行异常: %s", cb_err
        )
