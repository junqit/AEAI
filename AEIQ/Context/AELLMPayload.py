from dataclasses import dataclass
from enum import Enum
from typing import List, Dict


class LLMType(Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    ZHIPU = "zhipu"


class AEAiLevel(Enum):
    default = 1
    middle = 2
    high = 3


@dataclass
class AELLMPayload:
    messages: List[Dict[str, str]]
    llm_type: LLMType = LLMType.CHATGPT
    level: AEAiLevel = AEAiLevel.default

    def to_dict(self) -> dict:
        # llm_type 输出枚举值（如 "chatgpt"），level 输出成员名（如 "default"），
        # 与下游 llms 服务约定的字符串协议保持一致，避免硬编码字符串
        return {
            "messages": self.messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
        }
