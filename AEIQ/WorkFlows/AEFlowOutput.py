"""
AEFlowOutput - Flow 输出数据（普通类）。

持有 out_schema（输出数据 map）与 schema（输出结构定义 map）。
"""


class AEFlowOutput:
    """Flow 输出数据"""

    def __init__(self, out_schema: dict = None, schema: dict = None):
        
        # out_schema：输出数据（map）
        self.out_schema: dict = out_schema or {}
