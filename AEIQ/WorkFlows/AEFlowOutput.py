"""
AEFlowOutput - Flow 输出数据（普通类）。

持有 out_schema（输出数据 map）与 schema（输出结构定义 map）。
"""
from typing import Any

# out_schema 内 LLM 输出嵌套层的字段名
AE_LLM_OUT = "llm_out"


class AEFlowOutput:
    """Flow 输出数据"""

    def __init__(self, out_schema: dict = None, schema: dict = None):

        # out_schema：输出数据（map）
        self.out_schema: dict = out_schema or {}

    def add_param(self, key: str, value: Any) -> None:
        """向 out_schema 首层直接添加一个参数：key -> value。

        与 add_llm_out（写入 llm_out 嵌套层）对应，本方法写入 out_schema 首层；
        同名 key 覆盖。

        Args:
            key: out_schema 首层的字段名
            value: 该字段的值（任意类型）
        """
        self.out_schema[key] = value

    def add_llm_out(self, key: str, description: str) -> None:
        """向 llm_out 直接添加一个占位参数：key -> llm_generate(description)。

        out_schema 内无 llm_out 时自动创建；同名 key 覆盖。

        Args:
            key: llm_out 内的字段名
            description: 该字段的 LLM 生成描述，经 llm_generate 包成 <|description|> 占位符
        """
        from Context.Context.AELLMPayload import llm_generate
        llm_out = self.out_schema.setdefault(AE_LLM_OUT, {})
        llm_out[key] = llm_generate(description)

    def set_llm_out(self, llm_out: dict) -> None:
        """直接替换 out_schema 内的 llm_out 字段（整体覆盖，原 llm_out 不再保留）。

        与 add_llm_out（向 llm_out 内追加单个占位字段）对应，本方法用传入 dict 整体替换 llm_out。

        Args:
            llm_out: 新的 llm_out（map），整体写入 out_schema[AE_LLM_OUT]
        """
        self.out_schema[AE_LLM_OUT] = llm_out
