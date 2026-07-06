"""
AEFlowOutput - Flow 输出数据，Map 结构（继承 dict）。

以 out_schema（map）构造，dict 内容即 out_schema；
可直接用作 AELLMPayload.out_schema 约束 LLM 严格按该结构输出。
"""


class AEFlowOutput(dict):
    """Flow 输出数据（Map 结构）"""

    def __init__(self, out_schema: dict = None):
        super().__init__(out_schema or {})
