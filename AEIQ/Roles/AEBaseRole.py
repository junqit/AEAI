"""
AEBaseRole - 角色 Flow 基类。

所有角色 Flow 继承本类。单独成文件以避免与 WorkFlows.AEFlow 循环导入
（Roles.AERole 被 AEFlow 导入，本类需 import AEFlow）。
"""
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from Context.Context.AELLMPayload import llm_generate
from Roles.AERole import AERoleParamInfo, AEFlowRole

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
        from Roles.Reviewer.AEReviewer import AEReviewer
        mapping = {
            AEFlowRole.expert.value: AEAssistant,
            AEFlowRole.workgroup.value: AEWorkGroup,
            AEFlowRole.employee.value: AEEmployee,
            AEFlowRole.reviewer.value: AEReviewer,
        }
        flow_cls = mapping.get(role_type)
        if flow_cls is None:
            logger.warning("[AERole:%s] 未知角色 type=%r，无法创建角色 flow", cls.__name__, role_type)
            return None
        return flow_cls(flowOutput=AEFlowOutput({AE_IDENT: ident, AE_ANSWER: llm_generate("角色结论")}))
