"""
AEFlowInput - Flow 输入数据，持有 parameter（map）、state 与创建者 ident。

content / ident 必传（构造后只读）；goal 经 set/get 方法维护；state 为框架内部生命周期标记。
内部参数（_parameter / _state / _ident / _goal）外部不可直接修改，统一经 get/set 方法访问。
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
    """Flow 输入数据。

    content / ident 为必传（构造后只读）；goal 经 set/get 方法维护；state 为框架内部生命周期标记。
    内部参数（_parameter / _state / _ident / _goal）外部不可直接修改，统一经 get/set 方法访问。
    """

    def __init__(self, content: str, ident: str):
        self._parameter: Dict[str, Any] = {}
        if content:
            self._parameter[AE_CONTENT] = content
        self._state: AEFlowStatus = AEFlowStatus.start
        self._ident: str = ident
        self._goal: str = ""

    def get_content(self) -> str:
        """返回 parameter 内的 content（用户原始问题文本）；无则返回空串。"""
        return self._parameter.get(AE_CONTENT, "")

    @property
    def ident(self) -> str:
        """创建者 ident（只读，构造时确定）。"""
        return self._ident

    def get_goal(self) -> str:
        """返回角色/任务目标（优化后的问题）。"""
        return self._goal

    def set_goal(self, goal: str) -> None:
        """设置角色/任务目标（由 receiveOptimizeInput 填充）。"""
        self._goal = goal

    def get_state(self) -> AEFlowStatus:
        """返回输入生命周期状态（start / complete）。"""
        return self._state

    def set_state(self, state: AEFlowStatus) -> None:
        """设置输入生命周期状态（框架内部使用，如子流完成时置 complete）。"""
        self._state = state
