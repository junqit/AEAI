from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from common.aellm_enums import AELLMType, AEAiLevel


@dataclass
class AELLMPayload:
    messages: List[Dict[str, str]]
    llm_type: AELLMType = AELLMType.ZHIPU
    level: AEAiLevel = AEAiLevel.default
    # 标识 LLM 需要返回的数据结构（JSON Schema 或自定义结构描述），为空表示不约束
    out_schema: Optional[Dict[str, Any]] = None
    # 采样温度，范围 0.0 - 1.0
    temperature: float = 0.7

    def __post_init__(self):
        if not (0.0 <= self.temperature <= 1.0):
            raise ValueError(f"temperature 必须在 0.0 - 1.0 之间，当前值: {self.temperature}")

    def to_dict(self) -> dict:
        # llm_type 输出枚举值（如 "chatgpt"），level 输出成员名（如 "default"），
        # 与下游 llms 服务约定的字符串协议保持一致，避免硬编码字符串
        return {
            "messages": self.messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
            "out_schema": self.out_schema,
            "temperature": self.temperature,
        }
