from dataclasses import dataclass
from typing import List, Dict

from common.aellm_enums import AELLMType, AEAiLevel


@dataclass
class AELLMPayload:
    messages: List[Dict[str, str]]
    llm_type: AELLMType = AELLMType.ZHIPU
    level: AEAiLevel = AEAiLevel.default

    def to_dict(self) -> dict:
        # llm_type 输出枚举值（如 "chatgpt"），level 输出成员名（如 "default"），
        # 与下游 llms 服务约定的字符串协议保持一致，避免硬编码字符串
        return {
            "messages": self.messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
        }
