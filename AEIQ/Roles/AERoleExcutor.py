"""
AERoleExcutor - 角色执行 Flow，继承 AERole + 4 个能力 mixin。

能力 mixin（各自独立文件，AERoleExcutor 继承）：
  - AEExpertMixin  (AEExpert.py)  ：拆解能力（requestDecompose / receiveDecompose）
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
from WorkFlows.AEFlowInfo import AE_ANSWER, AE_CONFIRM
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import AEFlowRole
from Roles.AERole import AERole
from Roles.AEExpert import AEExpertMixin
from Roles.AEWorkGroup import AEWorkGroupMixin
from Roles.AEEmployee import AEEmployeeMixin
from Roles.AETask import AETaskMixin

logger = logging.getLogger(__name__)


class AERoleExcutorFunction(AEFunctional):
    """角色执行 Flow 专属回包功能性方法名。"""
    receiveDecompose = "receiveDecompose"
    receiveQuestionType = "receiveQuestionType"
    receiveScripts = "receiveScripts"


class AERoleExcutor(AERole, AEExpertMixin, AEWorkGroupMixin, AEEmployeeMixin, AETaskMixin):
    """角色执行 Flow：继承 4 个能力 mixin，由 self.role 决定当前层级行为。

    - expert/workgroup/employee：有下层可拆解 → requestDecompose（AEExpertMixin）
    - task：无下层 → requestQuestionType（AETaskMixin）
    """

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self._questionType: str = ""
        self.role: AEFlowRole = AEFlowRole.employee

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，串行 requestRoleInformation → requestOptimizeInput 后执行。"""
        if not super().startFlow(flowInput):
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），忽略", type(self).__name__, self.title, self.deepth)
            return
        self.requestRoleInformation()

    def receiveRolePrompt(self, data: dict) -> bool:
        """接收 rolePrompt 后，请求生成问题优化提示（requestOptimizeInput）。"""
        result = super().receiveRolePrompt(data)
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题：存入 optimizePromptResult，再请求拆解（requestDecompose）。"""
        result = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        confirm = data.get(AE_CONFIRM) if isinstance(data, dict) else None
        confirm = (confirm or "").strip() if isinstance(confirm, str) else ""
        if confirm:
            logger.info("[%s][%s][d=%s] 收到需确认信息:\n%s", type(self).__name__, self.title, self.deepth, confirm)
            return True
        self.optimizePromptResult = result or ""
        logger.info("[%s][%s][d=%s] 收到优化后的问题:\n%s", type(self).__name__, self.title, self.deepth, self.optimizePromptResult)
        self.requestDecompose()
        return True
