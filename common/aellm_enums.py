"""
AE LLM 共享枚举定义（单一来源）

llms 服务与 AEIQ 服务均从此处导入 AELLMType / AEAiLevel / AEQuestionType，
避免在多个服务内重复定义导致漂移。
"""
from enum import Enum


class AELLMType(Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    ZHIPU = "zhipu"
    QWEN = "qwen"


class AEAiLevel(Enum):
    default = 1
    middle = 2
    high = 3


class AEQuestionType(Enum):
    """问题类型：标识 LLM 请求的用途与模态，供 provider 按类型适配处理。"""
    text = "text"               # 纯文本问答（LLM 作答、总结等自由文本输出）
    structured = "structured"   # 结构化 JSON 输出（角色信息、目标生成、角色选择、任务拆解、背景确认、脚本选型、验证评分等）
    image = "image"             # 含图片的多模态请求
