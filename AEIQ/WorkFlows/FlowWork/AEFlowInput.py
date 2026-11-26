"""
AEFlowInput - Flow 输入数据，持有 parameter（map）、state 与创建者 ident。

content / ident 必传（构造后只读）；goal 经 set/get 方法维护；state 为框架内部生命周期标记。
内部参数（_parameter / _state / _ident / _goal）外部不可直接修改，统一经 get/set 方法访问。
"""
from enum import Enum
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from Roles.RoleBase.AERoleType import AEFlowRole


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

    def __init__(self, content: str, ident: str, role: Optional["AEFlowRole"] = None):
        self._parameter: Dict[str, Any] = {}
        if content:
            self._parameter[AE_CONTENT] = content
        self._state: AEFlowStatus = AEFlowStatus.start
        self._ident: str = ident
        self._goal: str = ""
        self._role: Optional["AEFlowRole"] = role

    # 返回 content，无则空串
    def get_content(self) -> str:
        return self._parameter.get(AE_CONTENT, "")

    # 创建者 ident（只读）
    @property
    def ident(self) -> str:
        return self._ident

    # 返回任务目标
    def get_goal(self) -> str:
        return self._goal

    # 有 goal 返回 goal，否则返回 content
    def get_target(self) -> str:
        return self.get_goal() or self.get_content()

    # 设置任务目标
    def set_goal(self, goal: str) -> None:
        self._goal = goal

    # 返回生命周期状态
    def get_state(self) -> AEFlowStatus:
        return self._state

    # 设置生命周期状态
    def set_state(self, state: AEFlowStatus) -> None:
        self._state = state

    # 返回创建时指定的角色
    def get_role(self) -> Optional["AEFlowRole"]:
        return self._role

    # 设置角色
    def set_role(self, role) -> None:
        self._role = role
