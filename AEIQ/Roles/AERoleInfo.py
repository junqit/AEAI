"""AERoleInfo - 角色信息属性基类。

持有角色相关属性（role / title / responsibility / rolePrompt），
经 cooperative __init__ 初始化。AERoleInformation / AERoleQuestionOptimize / AERoleBase 继承本类。
"""
from typing import Optional

from Roles.AERoleType import AEFlowRole


class AERoleInfo:
    """角色信息属性基类：持有角色相关属性，经 cooperative __init__ 初始化。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 角色层级：None 表示未归属分解层级（如 AERefiner 入口，requestRoleSelect 据此选全部角色）；
        # AERoleExcutor 等由 _role() / 派发方显式设置具体层级。
        self.role: Optional[AEFlowRole] = None
        # ----- 角色信息（角色专属，非 AEFlow 基类职责）-----
        self.title: str = ""             # 职称（运行时由 receiveRoleInfomation 或子类 __init__ 填充）
        self.responsibility: str = ""    # 职责要求（同上）
        self.rolePrompt: str = ""        # 角色 prompt（由 receiveRolePrompt 赋值）
