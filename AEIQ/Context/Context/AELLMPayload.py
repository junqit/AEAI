import json
from dataclasses import dataclass
from typing import List, Dict, Any

from common.aellm_enums import AELLMType, AEAiLevel
from Assistant.AERole import AERole

# out_schema 中标记「由 LLM 生成」的占位哨兵值：
# 取该值的字段为待生成字段，其余字段视为已填好的固定值，LLM 须原样保留
LLM_RESULT_PLACEHOLDER = "llm_result"


def _annotate_schema(value: Any, indent: int = 0) -> str:
    """递归生成 out_schema 的标注形态：哨兵字段标「待生成」，其余标「保持原值」。

    用于构造 LLM 指令文本（非合法 JSON，仅作结构说明），告知 LLM 哪些字段需生成、
    哪些字段须保持给定原值不变。
    """
    pad = "  " * indent
    child_pad = "  " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for k, v in value.items():
            lines.append(
                f"{child_pad}{json.dumps(k, ensure_ascii=False)}: {_annotate_schema(v, indent + 1)}"
            )
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for v in value:
            lines.append(f"{child_pad}{_annotate_schema(v, indent + 1)}")
        lines.append(f"{pad}]")
        return "\n".join(lines)
    if value == LLM_RESULT_PLACEHOLDER:
        return '"<由你生成>"  # 待生成'
    return f"{json.dumps(value, ensure_ascii=False)}  # 保持原值"


@dataclass
class AELLMPayload:
    
    messages: List[Dict[str, str]]
    # LLM 必须严格按该结构输出（始终存在）
    out_schema: Dict[str, Any]
    llm_type: AELLMType = AELLMType.ZHIPU
    level: AEAiLevel = AEAiLevel.default
    # 采样温度，范围 0.0 - 1.0
    temperature: float = 0.7

    def __post_init__(self):
        if not (0.0 <= self.temperature <= 1.0):
            raise ValueError(f"temperature 必须在 0.0 - 1.0 之间，当前值: {self.temperature}")

    def to_dict(self) -> dict:
        # 按 out_schema 输出：注入 system 指令，标注「待生成 / 保持原值」字段，
        # 要求 LLM 仅生成「待生成」字段，其余原样保留，最终输出合法 JSON
        messages = list(self.messages)
        instruction = (
            "请按以下结构输出合法 JSON，仅生成标记为「待生成」的字段，"
            "其余字段保持给定原值不变，不要输出任何 JSON 之外的文字或解释，结构如下：\n"
            + _annotate_schema(self.out_schema)
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
