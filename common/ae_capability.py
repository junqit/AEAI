"""
AECapability - LLM 能力协议（Protocol，非父类）。

规范三件事：
  1. 能力：Provider / Model 支持什么（模态、输出格式、问题类型、上限）
  2. 触发条件：什么场景下该选此 Provider（question_type / modality 匹配）
  3. 接收参数：调用方应传哪些参数（必选 / 可选），参数值用于规范输出

协议用途：供 RAG 或路由层按能力描述检索 / 匹配合适的 Provider，
参数清单用于规范调用方构建请求时的参数组装。
"""
from dataclasses import dataclass, field
from typing import List, Set, Dict, Any, Optional
from enum import Enum
from common.aellm_enums import AELLMType, AEQuestionType


class AEModality(str, Enum):
    """输入模态"""
    text = "text"
    image = "image"
    audio = "audio"
    video = "video"


class AEOutputFormat(str, Enum):
    """输出格式"""
    text = "text"
    json = "json"
    image = "image"


@dataclass
class AEParamSpec:
    """参数规范：描述一个参数的名称、类型、是否必选、取值范围与用途。"""
    name: str
    required: bool = False
    param_type: str = "str"           # str / int / float / bool / list / dict
    default: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "required": self.required,
            "type": self.param_type,
            "default": self.default,
            "min": self.min_value,
            "max": self.max_value,
            "description": self.description,
        }


@dataclass
class AECapability:
    """能力协议：声明能力、触发条件与接收参数，供 RAG 检索匹配 + 规范输出。"""

    # ==================== 标识 ====================
    llm_type: AELLMType
    name: str = ""                     # 能力名称（如 "Qwen 多模态问答"）

    # ==================== 1. 能力 ====================
    input_modalities: Set[AEModality] = field(default_factory=lambda: {AEModality.text})
    output_formats: Set[AEOutputFormat] = field(default_factory=lambda: {AEOutputFormat.text})
    question_types: Set[AEQuestionType] = field(default_factory=lambda: {AEQuestionType.text})
    max_context_tokens: int = 0
    max_output_tokens: int = 0
    supports_streaming: bool = False
    supports_tool_calls: bool = False

    # ==================== 2. 触发条件 ====================
    # 满足以下条件时，此能力可被选中（RAG 按这些字段匹配）
    trigger_question_types: Set[AEQuestionType] = field(default_factory=lambda: {AEQuestionType.text})
    trigger_modalities: Set[AEModality] = field(default_factory=lambda: {AEModality.text})
    trigger_keywords: List[str] = field(default_factory=list)   # RAG 关键词检索用

    # ==================== 3. 接收参数（规范输出） ====================
    params: List[AEParamSpec] = field(default_factory=lambda: [
        AEParamSpec(name="messages", required=True, param_type="list", description="消息列表"),
        AEParamSpec(name="temperature", required=False, param_type="float", default=0.7, min_value=0.0, max_value=1.0, description="采样温度"),
        AEParamSpec(name="max_tokens", required=False, param_type="int", default=4096, min_value=1, description="最大生成 token"),
        AEParamSpec(name="level", required=False, param_type="str", default="default", description="AI 级别"),
        AEParamSpec(name="question_type", required=False, param_type="str", default="text", description="问题类型"),
    ])

    # ==================== 匹配方法（供 RAG / 路由调用） ====================

    def matches(self, question_type: AEQuestionType = None,
                modality: AEModality = None,
                keyword: str = None) -> bool:
        """是否匹配触发条件（question_type / modality / keyword 任一命中即匹配）。"""
        if question_type is not None and question_type in self.trigger_question_types:
            return True
        if modality is not None and modality in self.trigger_modalities:
            return True
        if keyword is not None and any(keyword in kw for kw in self.trigger_keywords):
            return True
        return False

    def get_required_params(self) -> List[AEParamSpec]:
        """返回必选参数列表。"""
        return [p for p in self.params if p.required]

    def get_optional_params(self) -> List[AEParamSpec]:
        """返回可选参数列表。"""
        return [p for p in self.params if not p.required]

    def get_param(self, name: str) -> Optional[AEParamSpec]:
        """按名称取参数规范。"""
        for p in self.params:
            if p.name == name:
                return p
        return None

    def validate_param(self, name: str, value: Any) -> bool:
        """校验参数值是否合法（类型 + 范围）。"""
        spec = self.get_param(name)
        if spec is None:
            return False
        if value is None:
            return not spec.required
        # 类型校验
        type_map = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict}
        expected = type_map.get(spec.param_type)
        if expected and not isinstance(value, expected):
            return False
        # 范围校验
        if spec.min_value is not None and isinstance(value, (int, float)) and value < spec.min_value:
            return False
        if spec.max_value is not None and isinstance(value, (int, float)) and value > spec.max_value:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "llm_type": self.llm_type.value,
            "name": self.name,
            "input_modalities": [m.value for m in self.input_modalities],
            "output_formats": [f.value for f in self.output_formats],
            "question_types": [t.value for t in self.question_types],
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "supports_streaming": self.supports_streaming,
            "supports_tool_calls": self.supports_tool_calls,
            "trigger_question_types": [t.value for t in self.trigger_question_types],
            "trigger_modalities": [m.value for m in self.trigger_modalities],
            "trigger_keywords": self.trigger_keywords,
            "params": [p.to_dict() for p in self.params],
        }
