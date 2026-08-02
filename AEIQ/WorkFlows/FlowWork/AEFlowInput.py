"""
AEFlowInput - Flow 输入数据，持有 parameter（map）、state 与创建者 ident。
"""
from enum import Enum
from typing import Dict, Any


class AEFlowStatus(Enum):
    """Flow 执行状态"""
    default = 0            # 初始状态（未启动）
    start = 1              # 启动中
    processing = 2         # 执行中
    complete = 3           # 已完成


# parameter 内 content 字段名
AE_CONTENT = "content"


class AEFlowInput:
    """Flow 输入数据"""

    def __init__(self, content: str = "", ident: str = ""):
        self.parameter: Dict[str, Any] = {}
        if content:
            self.parameter[AE_CONTENT] = content
        self.state: AEFlowStatus = AEFlowStatus.default
        self.ident: str = ident
