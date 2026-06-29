"""
LLM 消息处理工具（共享）

供 llms 服务各模型在构造网关请求时复用。
"""
from typing import List, Dict, Any, Tuple

# 视为系统提示的角色：
# - "system"：标准系统角色
# - "context"：AEIQ 中用于承载上下文/角色信息（工作目录、role prompt 等）
SYSTEM_ROLES = {"system", "context"}


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
