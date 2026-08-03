"""
AEFlowOutput - Flow 输出数据。

持有 ident（必传，complete 回程路由用）与 out_schema（输出数据 map，不含 ident）。
"""
from typing import Any

# out_schema 内 LLM 输出嵌套层的字段名
AE_LLM_OUT = "llm_out"


class AEFlowOutput:
    """Flow 输出数据"""

    def __init__(self, ident: str, out_schema: dict = None):
        self.ident: str = ident
        self.out_schema: dict = out_schema or {}

    def add_param(self, key: str, value: Any) -> None:
        """向 out_schema 首层直接添加一个参数：key -> value。"""
        self.out_schema[key] = value

    def add_llm_out(self, key: str, description: str) -> None:
        """向 llm_out 直接添加一个占位参数：key -> llm_generate(description)。"""
        from Context.Context.AELLMPayload import llm_generate
        llm_out = self.out_schema.setdefault(AE_LLM_OUT, {})
        llm_out[key] = llm_generate(description)

    def set_llm_out(self, llm_out: dict) -> None:
        """直接替换 out_schema 内的 llm_out 字段（整体覆盖）。"""
        self.out_schema[AE_LLM_OUT] = llm_out
