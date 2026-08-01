"""
AERoleExcutor - 角色执行 Flow，继承 AERoleBase + AERoleChoice（角色选择能力）。

能力来源：
  - AERoleBase：角色基类（角色信息 / 问题优化 / role_brief / param_info / _role）
  - AERoleChoice：角色选择（requestRoleSelect / receiveRoleSelect）
  - 本类：角色目标就绪后的推进（requestRoleSelect hook）

执行链：
  startFlow → requestRoleInformation → receiveRoleInfomation → requestRolePrompt
  → receiveRolePrompt → requestOptimizeInput → receiveOptimizeInput → requestRoleSelect
    └─ 默认：requestRoleSelect 派发对应角色 subFlow（task 子类覆写为 requestScripts）

AERoleExcutor 为角色执行基类，task 执行能力（Script Generator）由 AETaskRole 提供；
expert/workgroup/employee 子类（AEExpertRole 等）继承本类，_role() 决定当前层级。
"""
import logging

from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_ANSWER
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Roles.AERoleType import AEFlowRole
from Roles.AERoleBase import AERoleBase
from Roles.AERoleChoice import AERoleChoice

logger = logging.getLogger(__name__)


class AERoleExcutor(AERoleBase, AERoleChoice):
    """角色执行 Flow：继承 AERoleBase + AERoleChoice，由 self.role 决定当前层级行为。

    - expert/workgroup/employee：有下层 → requestRoleSelect（AERoleChoice）派发下层角色
    - task：AETaskRole 覆写 requestRoleSelect → requestScripts（脚本执行）
    """

    @classmethod
    def _role(cls):
        return AEFlowRole.task

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self._questionType: str = ""
        self.role = self._role()

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input；基类未启动（非 default 状态）则错误完成，避免父 flow 等待卡死。"""
        if not super().startFlow(flowInput):
            logger.warning("[%s][d=%s] startFlow 失败：基类未启动（非 default 状态），以错误完成避免卡死",
                           self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "flow 启动失败"},
                AEFlowCompletEvent.error,
            )
            return
        self.requestRoleInformation()

    def receiveRolePrompt(self, data: dict) -> bool:
        """接收 rolePrompt：基类校验 map 并存储（失败则错误完成）；rolePrompt 就绪后请求问题优化。"""
        super().receiveRolePrompt(data)
        if not self.rolePrompt:
            return True  # 基类已错误完成（非 map 或为空）
        self.requestOptimizeInput()
        return True

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收角色目标：基类存储后 roleGoal 为空则错误完成；否则调 requestRoleSelect 推进。"""
        result = super().receiveOptimizeInput(data)  # AERoleQuestionOptimize 存储 roleGoal
        if not result or not self.roleGoal:
            logger.warning("[%s][d=%s] roleGoal 为空，以错误完成本 flow 避免卡死",
                           self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "问题优化失败"},
                AEFlowCompletEvent.error,
            )
            return True
        self.requestRoleSelect()
        return result
