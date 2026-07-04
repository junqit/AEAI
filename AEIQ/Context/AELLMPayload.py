import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from common.aellm_enums import AELLMType, AEAiLevel
from Assistant.AERole import AERole


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
        # out_schema 作为 role:system 消息置于 messages 首位：
        # 整体数据结构按 out_schema 输出，已存在的值保持不变，仅需将 "********" 处替换为实际内容
        messages = list(self.messages)
        if self.out_schema is not None:
            instruction = (
                "严格按照以下 out_schema 结构输出结果：整体数据结构按 out_schema 进行，"
                "已存在的值保持不变（无需修改），仅需将其中标记为 \"********\" 的位置"
                "替换为实际内容后输出。仅输出合法 JSON，不要输出任何 JSON 之外的文字或解释：\n"
                + json.dumps(self.out_schema, ensure_ascii=False, indent=2)
            )
            messages.insert(0, {"role": AERole.SYSTEM.value, "content": instruction})
        # llm_type 输出枚举值（如 "chatgpt"），level 输出成员名（如 "default"），
        # 与下游 llms 服务约定的字符串协议保持一致，避免硬编码字符串
        return {
            "messages": messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
            "temperature": self.temperature,
        }
