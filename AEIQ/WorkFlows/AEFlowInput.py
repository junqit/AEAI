"""
AEFlowInput - Flow 输入数据，持有 content。
"""


class AEFlowInput:
    """Flow 输入数据"""

    def __init__(self, content: str = ""):
        self.content: str = content
