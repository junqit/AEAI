"""
AE LLM 共享枚举定义（单一来源）

llms 服务与 AEIQ 服务均从此处导入 AELLMType / AEAiLevel，
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
