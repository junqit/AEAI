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
        # 遍历 out_schema，分类占位符字段（需填写）与非占位符字段（不可修改）
        fill_fields: List[str] = []
        fixed_fields: List[str] = []

        def _walk(obj, path: str = ""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    p = f"{path}.{k}" if path else k
                    if isinstance(v, str) and is_llm_placeholder(v):
                        fill_fields.append(f"{p} ← {v}")
                    elif isinstance(v, (dict, list)):
                        _walk(v, p)
                    else:
                        fixed_fields.append(f"{p} = {v!r}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _walk(v, f"{path}[{i}]")

        _walk(self.out_schema)

        fill_list = "\n".join(f"  - {f}" for f in fill_fields) or "  (无)"
        fixed_list = "\n".join(f"  - {f}" for f in fixed_fields) or "  (无)"

        messages = list(self.messages)
        instruction = (
            "请按以下完整结构输出合法 JSON 对象，不要输出任何 JSON 之外的文字或解释，结构如下：\n"
            + schema_json
            + f"\n\n【不可修改的字段】（共 {len(fixed_fields)} 个，必须保持原值不变）：\n{fixed_list}"
            + "\n\n规则："
            "\n1. 必须返回上述完整 JSON 对象！"
            "\n2. 只可替换 <|描述|> 占位符的内容，不可修改、删除、新增占位符以外的任何字段名、字段值或结构；"
            "\n3. 字符串值内若包含双引号须转义为 \\\"。"
            "\n4. 仅修改指定位置，其余字符必须逐字保持一致（byte-for-byte identical）。除非我明确要求，否则不得修改任何字符，包括空格、标点、大小写和换行。"
        )
        messages.insert(0, {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: instruction})
        return {
            "messages": messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
            "temperature": self.temperature,
        }
