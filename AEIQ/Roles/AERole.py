from enum import Enum

# LLM 消息 dict 的字段名
AE_ROLE = "role"
AE_CONTENT = "content"

# 用户问题在上下文中的统一标识前缀（含书名号，system 消息 / 摘要引用均用此常量，保持一致）
AE_USER_QUESTION_PREFIX = "「当前用户的问题是：」"


class AEConentRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    CONTEXT = "context"


class AEFlowRole(Enum):
    """Flow 角色类型：专家 / 工作组 / 员工 / 评审者"""
    expert = "expert"        # 专家
    workgroup = "workgroup"  # 工作组
    employee = "employee"    # 员工
    reviewer = "reviewer"    # 评审者
