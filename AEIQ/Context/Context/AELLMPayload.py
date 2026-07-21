import json
import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any

from common.aellm_enums import AELLMType, AEAiLevel
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT
from WorkFlows.AEFlowOutput import AE_LLM_OUT

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

    def _extract_content_template(self):
        """取出 out_schema 最内层的「内容模板」——占位符所在层，不含任何 ident / 路由信封。

        信封每层形如 {ident, title[, excutor], llm_out: <下一层>}；沿 llm_out 下钻，
        直到某层的 llm_out 不再是「含 llm_out 的 dict」，即为内容模板（dict / list / 占位结构）。
        """
        node = self.out_schema
        while isinstance(node, dict) and AE_LLM_OUT in node:
            child = node[AE_LLM_OUT]
            if isinstance(child, dict) and AE_LLM_OUT in child:
                node = child
            else:
                return child
        return node

    def to_llm_request_dic(self) -> dict:
        # 两步流程·第一步：仅把「内容模板」（含占位符、无 ident）发给 LLM，让其填充 / 展开
        content_template = self._extract_content_template()
        template_json = json.dumps(content_template, ensure_ascii=False, indent=2)
        messages = list(self.messages)
        instruction = (
            "请按以下完整结构输出合法 JSON，不要输出任何 JSON 之外的文字或解释，结构如下：\n"
            + template_json
            + "\n\n规则："
            "\n1. 必须返回上述完整 JSON，包含所有字段；"
            "\n2. 只可替换 <|描述|> 占位符的内容，不可修改、删除、新增占位符以外的任何字段名或结构；"
            "\n3. 若某数组只含一个模板元素，可按需生成多个同结构元素；"
            "\n4. 字符串值内若包含双引号须转义为 \\\"。"
        )
        messages.insert(0, {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: instruction})
        return {
            "messages": messages,
            "llm_type": self.llm_type.value,
            "level": self.level.name,
            "temperature": self.temperature,
        }

    def fill_content(self, filled_content) -> dict:
        """两步流程·第二步：把 LLM 生成的内容回填到信封最内层 llm_out，返回完整信封（含可信 ident，逐字保留）。"""
        import copy
        envelope = copy.deepcopy(self.out_schema)
        node = envelope
        while isinstance(node, dict) and AE_LLM_OUT in node:
            child = node[AE_LLM_OUT]
            if isinstance(child, dict) and AE_LLM_OUT in child:
                node = child
            else:
                node[AE_LLM_OUT] = filled_content
                break
        return envelope
