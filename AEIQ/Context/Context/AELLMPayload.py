import json
import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any

from common.aellm_enums import AELLMType, AEAiLevel
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT

logger = logging.getLogger(__name__)


class AEEnvParamType(Enum):
    """环境参数类型枚举"""
    python = "python"
    ruby = "ruby"
    shell = "shell"
    system = "system"


def llm_generate(description: str = "描述信息") -> str:
    """LLM 生成占位符：<|描述|>。

    <||> 之间的 description 用来说明该位置应填充什么内容，
    发送时作为模板占位，回包由 LLM 根据 description 生成实际内容替换。
    """
    return f"<|{description}|>"


# 占位符正则：<|...|> 形式的字符串均为 LLM 占位符
LLM_PLACEHOLDER_RE = re.compile(r"^<\|(.+)\|>$")


def is_llm_placeholder(value: Any) -> bool:
    """判断 value 是否为 LLM 占位符（<|描述|> 形式）。"""
    return isinstance(value, str) and bool(LLM_PLACEHOLDER_RE.match(value))


@dataclass
class AELLMPayload:

    messages: List[Dict[str, str]]
    # LLM 必须严格按该结构输出（始终存在）
    out_schema: Dict[str, Any]
    llm_type: AELLMType = AELLMType.ZHIPU
    level: AEAiLevel = AEAiLevel.default
    # 采样温度，范围 0.0 - 1.0
    temperature: float = 0.7
    # 环境参数配置（私有，默认包含 system，表示默认携带系统信息）；外部经 add/remove_env_param 管理
    _env_params: List[AEEnvParamType] = field(
        default_factory=lambda: [AEEnvParamType.system], init=False, repr=False,
    )

    def __post_init__(self):
        if not (0.0 <= self.temperature <= 1.0):
            raise ValueError(f"temperature 必须在 0.0 - 1.0 之间，当前值: {self.temperature}")

    # ==================== env_params 管理（私有字段，外部仅经以下方法访问） ====================

    def add_env_param(self, param: AEEnvParamType) -> None:
        """添加环境参数；已存在则跳过。"""
        if param not in self._env_params:
            self._env_params.append(param)

    def remove_env_param(self, param: AEEnvParamType) -> None:
        """移除环境参数；不存在则跳过。"""
        if param in self._env_params:
            self._env_params.remove(param)

    @property
    def env_params(self) -> List[AEEnvParamType]:
        """返回当前携带的环境参数列表（副本）。"""
        return list(self._env_params)

    def to_llm_request_dic(self) -> dict:
        # 按 out_schema 输出：注入 system 指令，要求按该结构输出合法 JSON
        schema_json = json.dumps(self.out_schema, ensure_ascii=False, indent=2)
        logger.info("out_schema 结构:\n%s", schema_json)
        messages = list(self.messages)
        instruction = (
            "请按以下结构输出合法 JSON，不要输出任何 JSON 之外的文字或解释，结构如下：\n"
            + schema_json
            + "\n\n其中形如 \"<|描述|>\" 的字符串值为占位符，<||> 之间的描述说明了该位置应填充的内容；"
            "请根据用户问题及占位符描述生成实际内容后替换该占位符；"
            "其余字段与元信息保持原值不变，仅按原结构回填。"
        )
        messages.insert(0, {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: instruction})
        # llm_type 输出枚举值（如 "chatgpt"），level 输出成员名（如 "default"），
        # 与下游 llms 服务约定的字符串协议保持一致，避免硬编码字符串
        return {
            "messages": messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
            "temperature": self.temperature,
        }
