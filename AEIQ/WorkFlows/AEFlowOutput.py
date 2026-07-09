"""
AEFlowOutput - Flow 输出数据（普通类）。

持有 out_schema（输出数据 map）与 schema（输出结构定义 map）。
"""


class AEFlowOutput:
    """Flow 输出数据"""

    def __init__(self, out_schema: dict = None, schema: dict = None):
        
        # out_schema：输出数据（map）
        self.out_schema: dict = out_schema or {}

    def add_llm_out(self, key: str, description: str) -> None:
        """向 llm_out 直接添加一个占位参数：key -> llm_generate(description)。

        out_schema 内无 llm_out 时自动创建；同名 key 覆盖。

        Args:
            key: llm_out 内的字段名
            description: 该字段的 LLM 生成描述，经 llm_generate 包成 <|description|> 占位符
        """
        from Context.Context.AELLMPayload import llm_generate
        llm_out = self.out_schema.setdefault("llm_out", {})
        llm_out[key] = llm_generate(description)
