"""
AERole - 角色 Flow 基类。

所有角色 Flow 继承本类。角色常量/枚举（AEConentRole / AEFlowRole / ROLE_PARAMS 等）
在 Roles.AERoleType 中；本类仅定义 AERole 角色基类（需 import AEFlow，故与常量分文件，
避免与 WorkFlows.AEFlow 循环导入）。
"""
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from Context.Context.AELLMPayload import llm_generate
from Roles.AERoleType import AERoleParamInfo, AEFlowRole, ROLE_PARAMS

logger = logging.getLogger(__name__)


class AERole(AEFlow):
    """角色 Flow 基类。"""

    roleParamInfo: Optional[AERoleParamInfo] = None

    @classmethod
    def createRoleFlow(cls, role_type: str, ident: str):
        """根据角色 type 创建对应角色 Flow（output.ident 路由回 ident）；未知 type 返回 None。

        角色 Flow 类按需懒导入，避免与子类形成循环导入。

        Args:
            role_type: 角色 type 字符串（expert / workgroup / employee / reviewer）
            ident: 角色 flow 完成时回程路由目标 ident（通常为 delegate.ident）

        Returns:
            角色 Flow 实例；未知 type 时返回 None
        """
        from Roles.Assistant.AEAssistant import AEAssistant
        from Roles.WorkGroup.AEWorkGroup import AEWorkGroup
        from Roles.Employee.AEEmployee import AEEmployee
        from Roles.AETask import AETask
        from Roles.Reviewer.AEReviewer import AEReviewer
        from Roles.LLM.AELLMRole import AELLMRole
        mapping = {
            AEFlowRole.expert.value: AEAssistant,
            AEFlowRole.workgroup.value: AEWorkGroup,
            AEFlowRole.employee.value: AEEmployee,
            AEFlowRole.task.value: AETask,
            AEFlowRole.reviewer.value: AEReviewer,
            AEFlowRole.llm.value: AELLMRole,
        }
        flow_cls = mapping.get(role_type)
        if flow_cls is None:
            logger.warning("[AERole:%s] 未知角色 type=%r，无法创建角色 flow", cls.__name__, role_type)
            return None
        return flow_cls(flowOutput=AEFlowOutput({AE_IDENT: ident, AE_ANSWER: llm_generate("角色结论")}))

    def roleDescription(self) -> str:
        """角色描述：拼接 ROLE_PARAMS 全部角色的花名册（type / 职称 / 职责），供角色选择等场景使用。

        子类可覆写为仅返回自身角色的描述。
        """
        lines = []
        for role, info in ROLE_PARAMS.items():
            lines.append(f"- type: {role.value}；职称：{info.title}；职责：{info.responsibility}")
        return "\n".join(lines)
