from enum import Enum

# LLM 消息 dict 的字段名
AE_ROLE = "role"
AE_CONTENT = "content"

# 用户问题在上下文中的统一标识前缀（含书名号，system 消息 / 摘要引用均用此常量，保持一致）
AE_USER_QUESTION_PREFIX = "「当前用户的问题是：」"


class AERole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    CONTEXT = "context"
