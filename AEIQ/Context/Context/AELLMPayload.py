import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Any

from common.aellm_enums import AELLMType, AEAiLevel
from Assistant.AERole import AERole

logger = logging.getLogger(__name__)

# LLM 生成占位符：out_schema 中需由 LLM 生成内容的字段值
# 发送时作为模板占位，回包由 LLM 替换为实际生成内容
llm_generate = "<|描述信息|>"


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
        # 按 out_schema 输出：注入 system 指令，要求按该结构输出合法 JSON
        schema_json = json.dumps(self.out_schema, ensure_ascii=False, indent=2)
        logger.info("out_schema 结构:\n%s", schema_json)
        messages = list(self.messages)
        instruction = (
            "请按以下结构输出合法 JSON，不要输出任何 JSON 之外的文字或解释，结构如下：\n"
            + schema_json
            + f"\n\n其中字符串值 \"{llm_generate}\" 为占位符，需由你根据用户问题生成实际内容后替换；"
            "其余字段与元信息保持原值不变，仅按原结构回填。"
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
