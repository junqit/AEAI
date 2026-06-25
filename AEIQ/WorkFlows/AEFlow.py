"""
AEFlow - WorkFlow 中单个 Flow 的接口定义（Protocol）
任何类只要实现了对应的属性和方法即视为符合接口，无需继承
"""
import json
from typing import Dict, Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class AEFlow(Protocol):
    """Flow 接口协议，任何类实现以下属性和方法即可"""

    flow_id: str
    name: str
    description: str
    output_schema: dict

    def build_prompt(self, context: Dict[str, Any]) -> str: ...

    def build_output_instruction(self) -> str: ...

    def build_full_prompt(self, context: Dict[str, Any]) -> str: ...

    def parse_response(self, llm_output: str) -> Optional[Dict[str, Any]]: ...


def build_output_instruction(output_schema: dict) -> str:
    schema_str = json.dumps(output_schema, ensure_ascii=False, indent=2)
    return (
        f"你必须严格按以下 JSON 结构输出，不要输出任何 JSON 之外的文字：\n\n"
        f"{schema_str}"
    )


def build_full_prompt(prompt: str, output_schema: dict) -> str:
    output_instruction = build_output_instruction(output_schema)
    return f"{prompt}\n\n[输出格式要求]\n{output_instruction}"


def parse_response(llm_output: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(llm_output.strip())
    except json.JSONDecodeError:
        return None
