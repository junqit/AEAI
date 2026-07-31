"""
AERoleExcutor - 角色执行 Flow，继承 AERoleBase + AERoleChoice（角色选择能力）。

能力来源：
  - AERoleBase：角色基类（角色信息 / 问题优化 / role_brief / param_info / _role）
  - AERoleChoice：角色选择（requestRoleSelect / receiveRoleSelect）+ 直接作答（requestDirectAnswer）
  - 本类：角色目标就绪后的推进（_after_role_goal hook）

执行链：
  startFlow → requestRoleInformation → receiveRoleInfomation → requestRolePrompt
  → receiveRolePrompt → requestOptimizeInput → receiveOptimizeInput → _after_role_goal
    └─ 默认：requestRoleSelect 派发对应角色 subFlow（task 子类覆写为 requestScripts）

AERoleExcutor 为角色执行基类，task 执行能力（Script Generator）由 AETaskRole 提供；
expert/workgroup/employee 子类（AEExpertRole 等）继承本类，_role() 决定当前层级。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER, AE_CONFIRM
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Roles.AERoleType import AEFlowRole
from Roles.AERoleBase import AERoleBase
from Roles.AERoleChoice import AERoleChoice

logger = logging.getLogger(__name__)


class AERoleExcutor(AERoleBase, AERoleChoice):
    """角色执行 Flow：继承 AERoleBase + AERoleChoice，由 self.role 决定当前层级行为。

    - expert/workgroup/employee：有下层 → requestRoleSelect（AERoleChoice）派发下层角色
    - task：AETaskRole 覆写 _after_role_goal → requestScripts（脚本执行）
    - 选 llm → requestDirectAnswer（本类，派发 AELLMRole）
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
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），以错误完成避免卡死",
                           type(self).__name__, self.title, self.deepth)
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
        """接收角色目标：confirm 则暂停；基类存储后 roleGoal 为空则错误完成；否则交 _after_role_goal 推进。"""
        confirm = data.get(AE_CONFIRM) if isinstance(data, dict) else None
        confirm = (confirm or "").strip() if isinstance(confirm, str) else ""
        if confirm:
            return True
        result = super().receiveOptimizeInput(data)  # AERoleQuestionOptimize 存储 roleGoal
        if not result or not self.roleGoal:
            logger.warning("[%s][%s][d=%s] roleGoal 为空，以错误完成本 flow 避免卡死",
                           type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "问题优化失败"},
                AEFlowCompletEvent.error,
            )
            return True
        self._after_role_goal()
        return result

    def _after_role_goal(self) -> None:
        """角色目标就绪后的下一步（hook，子类覆写）：默认请求角色选择。"""
        self.requestRoleSelect()

    def requestDirectAnswer(self) -> None:
        """无需脚本时，派发 AELLMRole 直接作答（兄弟 flow，input 取角色目标）。"""
        if self.delegate is None:
            logger.warning("[%s][%s][d=%s] delegate 未设置，无法派发 AELLMRole", type(self).__name__, self.title, self.deepth)
            return
        delegate_ident = self.delegate.ident
        sub = self._instantiate_role_flow(AEFlowRole.llm, delegate_ident)
        self.delegate.receive_add_flow(sub)
        content = self.roleGoal or (self.input.content if self.input is not None else "")
        sub.startFlow(AEFlowInput(content=content))
        self.flow_receive_complete(
            {AE_IDENT: delegate_ident, AE_ANSWER: self.roleGoal},
            AEFlowCompletEvent.default,
        )
