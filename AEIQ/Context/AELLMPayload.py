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
        # 以 role:system 消息置于 messages 首位：
        # - 已存在的值保持不变，值为空字符串的字段替换为实际内容
        # - 每层若无值（None / ""），代表让 LLM 根据上下文生成该层的 JSON 结构
        messages = list(self.messages)
        if self.out_schema is not None:
            # 判断每层是否有空值（None / ""）
            has_empty = False
            cur = self.out_schema
            while isinstance(cur, dict):
                inner = cur.get("llm_out")
                if inner is None or inner == "":
                    has_empty = True
                    break
                cur = inner
            parts = [
                "以下 JSON 结构是要求输出的数据结构，请严格按照该结构输出：",
                "整体数据结构按给出的结构进行，已存在的值保持不变（无需修改）；",
                "其中值为空字符串的字段，请根据上述对话内容（prompt）填入对应的实际内容；",
            ]
            if has_empty:
                parts.append(
                    "其中 llm_out 为空（null/无值）的位置，请根据用户的问题"
                    "生成该层对应的 JSON 数据结构。"
                )
            parts.append("仅输出合法 JSON，不要输出任何 JSON 之外的文字或解释，结构如下：\n")
            parts.append(json.dumps(self.out_schema, ensure_ascii=False, indent=2))
            instruction = "".join(parts)
            messages.insert(0, {"role": AERole.SYSTEM.value, "content": instruction})
        # llm_type 输出枚举值（如 "chatgpt"），level 输出成员名（如 "default"），
        # 与下游 llms 服务约定的字符串协议保持一致，避免硬编码字符串
        return {
            "messages": messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
            "temperature": self.temperature,
        }
