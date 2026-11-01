"""AERoleExcutor - 角色执行 Flow。

执行链：
  on_flow_start → requestRoleInformation → receiveRoleInfomation
  → requestOptimizeInput → receiveOptimizeInput → requestRoleChoice → receiveRoleChoice
  → _execute_leaf（llm/script 自身执行）| requestWorkflow → receiveWorkflow → receive_summarize_result

role 在 roleChoice 后确认（初始为 None）。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Roles.Excutor.AERoleExcuteLLM import AERoleExcuteLLM
from Roles.Excutor.AERoleExcuterScript import AERoleExcuterScript
from Roles.RoleBase.AERoleBase import AERoleBase
from Roles.RoleBase.AERoleType import AE_LEAF_ROLES, AEFlowRole

logger = logging.getLogger(__name__)


class AERoleExcutor(AERoleExcuteLLM, AERoleExcuterScript, AERoleBase):
    """角色执行 Flow：自带前置链路（角色信息/问题优化/角色选择/任务拆解），并经继承获得 llm/script
    执行能力（AERoleExcuteLLM / AERoleExcuterScript）。叶子角色（llm/script）自身执行；协调角色按规则拆解。
    叶子自执行、任务拆解由基类 AERoleWorkflow._dispatch_workflow_tasks 直接派发子 AERoleExcutor。
    """

    # 启动 flow；基类未启动则错误完成避免卡死。
    def on_flow_start(self, flowInput=None) -> bool:
        if not super().on_flow_start(flowInput):
            logger.warning("[%s][d=%s] on_flow_start 失败：基类未启动", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "flow 启动失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRoleInformation()
        return True

    # 接收角色信息；成功推进问题优化，失败则错误完成闭环。
    def receiveRoleInfomation(self, data: dict) -> bool:
        result = super().receiveRoleInfomation(data)
        if not result or not self.title or not self.responsibility:
            logger.warning("[%s][d=%s] title 或 responsibility 为空，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "角色信息（title/responsibility）生成失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestOptimizeInput()
        return result

    # 接收角色选择；叶子角色自身执行，协调角色按规则拆解。
    def receiveRoleChoice(self, data: dict) -> bool:
        result = super().receiveRoleChoice(data)
        if not result or self.role is None:
            logger.warning("[%s][d=%s] 角色选择失败，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "角色选择失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.print_info()
        role_enum = self.role.role if self.role is not None else None
        if role_enum in AE_LEAF_ROLES:
            # 叶子角色（llm/script）：自身执行（llm→requestLLMAnswer，script→start_flow），不再派发子 flow
            self._execute_leaf(role_enum)
            return result
        if self.role is not None and self.role.workflow_rule:
            self.requestWorkflow()
        else:
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: (self.input.get_goal() or self.input.get_content()) if self.input is not None else ""},
            )
        return result

    # 叶子角色自身执行：llm→requestLLMAnswer，script→start_flow。
    def _execute_leaf(self, role_enum: AEFlowRole) -> bool:
        if role_enum == AEFlowRole.llm:
            logger.info("[%s][d=%s] 叶子角色 llm 自身作答", self.title, self.deepth)
            return self.requestLLMAnswer()
        if role_enum == AEFlowRole.script:
            logger.info("[%s][d=%s] 叶子角色 script 自身执行脚本循环", self.title, self.deepth)
            self.start_flow()
            return True
        logger.warning("[%s][d=%s] 未登记的叶子角色 %s，以错误完成本 flow 避免卡死",
                       self.title, self.deepth, role_enum.value)
        self.flow_complete(
            {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
             AE_CONTENT: "未登记的叶子角色"},
            AEFlowCompletEvent.error,
        )
        return False

    # 接收优化后目标；为空则错误完成，否则推进角色选择。
    def receiveOptimizeInput(self, data: dict) -> bool:
        result = super().receiveOptimizeInput(data)  # 存储 input.goal
        if not result or not (self.input.get_goal() if self.input is not None else ""):
            logger.warning("[%s][d=%s] input.goal 为空，以错误完成本 flow 避免卡死",
                           self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "问题优化失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRoleChoice()
        return result
