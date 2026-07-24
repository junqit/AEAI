"""
AEEmployee - 员工 Flow，继承 AERoleExcutor。

完成单一流水线的工作：承接上游分配的一条流水线，调用 LLM / Tools 执行其各环节，
产出可被上游整合的结构化结果。

执行链（角色信息→问题优化→执行类型判定→脚本/直接作答）由 AERoleExcutor 提供，
本类仅定义员工角色的 title / responsibility / roleDescription。
"""
import logging

from WorkFlows.AEFlowOutput import AEFlowOutput
from Roles.AERoleType import AEFlowRole, get_role_param
from Roles.AERoleExcutor import AERoleExcutor

logger = logging.getLogger(__name__)


class AEEmployee(AERoleExcutor):
    """员工 Flow：完成单一流水线的工作。执行逻辑继承自 AERoleExcutor。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "Employee"
        self.responsibility = (
            "完成单一流水线的工作。\n"
            "要求：\n"
            "1. 仅负责本流水线的执行，不跨流水线、不跨维度规划与决策。\n"
            "2. 调用模型或工具完成流水线各环节（检索 / 分析 / 生成 / 转换等）。\n"
            "3. 产出可直接被上游整合的结构化结果。\n"
            "4. 遇到不明确处向上回传，由工作组或专家裁决。"
        )

    def roleDescription(self) -> str:
        """角色描述：返回本角色（员工）的职称与职责。"""
        info = get_role_param(AEFlowRole.employee)
        return f"{info.title}：{info.responsibility}"
