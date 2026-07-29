"""
AERoleExcutor - 角色执行 Flow，继承 AERole + 4 个能力 mixin。

能力 mixin（各自独立文件，AERoleExcutor 继承）：
  - AERoleDecompose (AERoleDecompose.py)：拆解能力（requestDecompose / receiveDecompose）
  - AEWorkGroupMixin (AEWorkGroup.py)：工作组扩展（预留）
  - AEEmployeeMixin (AEEmployee.py)  ：员工扩展（预留）
  - AETaskMixin    (AETask.py)     ：执行能力（requestQuestionType / requestScripts / ...）

执行链：
  startFlow → requestRoleInformation → receiveRoleInfomation → requestRolePrompt
  → receiveRolePrompt → requestOptimizeInput → receiveOptimizeInput → requestDecompose
    ├─ 可拆解：receiveDecompose 创建 subFlow（递归拆解，完成后汇总）
    └─ 已原子：requestQuestionType → script / llm

单一类承担 expert/workgroup/employee/task 角色：由 self.role(AEFlowRole) 标记当前层级。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER, AE_CONFIRM
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import AEFlowRole
from Roles.AERole import AERole
from Roles.AERoleDecompose import AERoleDecompose
from Roles.AEWorkGroup import AEWorkGroupMixin
from Roles.AEEmployee import AEEmployeeMixin
from Roles.AETask import AETaskMixin

logger = logging.getLogger(__name__)


class AERoleExcutorFunction(AEFunctional):
    """角色执行 Flow 专属回包功能性方法名。"""
    receiveDecompose = "receiveDecompose"
    receiveQuestionType = "receiveQuestionType"
    receiveScripts = "receiveScripts"


class AERoleExcutor(AERole, AERoleDecompose, AEWorkGroupMixin, AEEmployeeMixin, AETaskMixin):
    """角色执行 Flow：继承 4 个能力 mixin，由 self.role 决定当前层级行为。

    - expert/workgroup/employee：有下层可拆解 → requestDecompose（AERoleDecompose）
    - task：无下层 → requestQuestionType（AETaskMixin）
    """

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self._questionType: str = ""
        self.role = AEFlowRole.employee

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
        """接收 rolePrompt：基类存储后 rolePrompt 仍为空则错误完成；否则请求生成问题优化提示。"""
        result = super().receiveRolePrompt(data)
        if not result or not self.rolePrompt:
            logger.warning("[%s][%s][d=%s] rolePrompt 为空，以错误完成本 flow 避免卡死",
                           type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "角色提示生成失败"},
                AEFlowCompletEvent.error,
            )
            return True
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题：confirm 则暂停；基类存储后 optimizePromptResult 仍为空则错误完成；否则请求拆解。"""
        confirm = data.get(AE_CONFIRM) if isinstance(data, dict) else None
        confirm = (confirm or "").strip() if isinstance(confirm, str) else ""
        if confirm:
            return True
        result = super().receiveOptimizeInput(data)  # 基类存储 optimizePromptResult + 打印摘要
        if not result or not self.optimizePromptResult:
            logger.warning("[%s][%s][d=%s] optimizePromptResult 为空，以错误完成本 flow 避免卡死",
                           type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "问题优化失败"},
                AEFlowCompletEvent.error,
            )
            return True
        self.requestDecompose()
        return result
