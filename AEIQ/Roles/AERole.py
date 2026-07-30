"""
AERole - 角色 Flow 基类。

所有角色 Flow 继承本类。角色常量/枚举（AEConentRole / AEFlowRole / ROLE_PARAMS 等）
在 Roles.AERoleType 中；角色选择能力在 Roles.AERoleChoice 中（AERole 继承获得）。
本类仅定义 AERole 角色基类（需 import AEFlow，故与常量分文件，避免与 WorkFlows.AEFlow 循环导入）。
"""
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInput import AEFlowInput
from Roles.AERoleType import AERoleParamInfo, AEFlowRole, ROLE_PARAMS
from Roles.AERoleChoice import AERoleChoice

logger = logging.getLogger(__name__)


class AERole(AEFlow, AERoleChoice):
    """角色 Flow 基类。继承 AERoleChoice 获得 requestRoleSelect 等角色选择能力。"""

    roleParamInfo: Optional[AERoleParamInfo] = None

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        super().__init__(flowOutput=flowOutput, ident=ident, flowInput=flowInput)
        # 角色层级：None 表示未归属分解层级（如 AERefiner 入口，requestRoleSelect 据此选全部角色）；
        # AERoleExcutor 由派发方（refiner / decompose / supplement）显式设置具体层级。
        self.role: Optional[AEFlowRole] = None

    def roleDescription(self) -> str:
        """角色描述：拼接 ROLE_PARAMS 全部角色的花名册（type / 职称 / 职责），供角色选择等场景使用。

        子类可覆写为仅返回自身角色的描述。
        """
        lines = []
        for role, info in ROLE_PARAMS.items():
            lines.append(f"- type: {role.value}；职称：{info.title}；职责：{info.responsibility}")
        return "\n".join(lines)
