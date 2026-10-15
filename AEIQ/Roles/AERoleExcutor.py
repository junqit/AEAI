"""AERoleExcutor - 角色执行 Flow。

执行链：
  on_flow_start → requestRoleInformation → receiveRoleInfomation
  → requestOptimizeInput → receiveOptimizeInput → requestRoleChoice → receiveRoleChoice
  → requestWorkflow → receiveWorkflow → receive_summarize_result

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

    def on_flow_start(self, flowInput) -> bool:
        """启动：基类置 input；未启动则错误完成，避免父 flow 等待卡死。"""
        if not super().on_flow_start(flowInput):
            logger.warning("[%s][d=%s] on_flow_start 失败：基类未启动", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "flow 启动失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRoleInformation()
        return True

    def receiveRoleInfomation(self, data: dict) -> bool:
        """接收角色信息：判断基类处理结果决定下一步（闭环 / 推进）。
        基类写入 title/responsibility，成功返回 True；失败（任一为空）返回 False（基类不闭环）。
        成功则推进 requestOptimizeInput（问题优化）；失败则以错误完成本 flow 闭环避免卡死，并返回 False 如实反映失败。"""
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

    def receiveRoleChoice(self, data: dict) -> bool:
        """接收角色选择：基类设 self.role；叶子角色（llm/script）自身执行（不经子 flow）；
        协调角色有拆解规则则推进 requestWorkflow，无则直接完成。"""
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
        role_enum = self.role.role
        if role_enum in AE_LEAF_ROLES:
            # 叶子角色（llm/script）：自身执行（llm→requestLLMAnswer，script→start_flow），不再派发子 flow
            return self._execute_leaf(role_enum)
        if self.role.workflow_rule:
            self.requestWorkflow()
        else:
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: (self.input.get_goal() or self.input.get_content()) if self.input is not None else ""},
            )
        return result

    def _execute_leaf(self, role_enum: AEFlowRole) -> bool:
        """叶子角色（llm/script）自身执行：llm→requestLLMAnswer（AERoleExcuteLLM），
        script→start_flow（AERoleExcuterScript）。前置链路已就绪 title/goal，直接执行不再派发子 flow。
        回包经基类 receive_summarize_result（llm）或脚本循环各 receive* 回包（script）完成本 flow。"""
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

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收角色目标：基类存储后 input.goal 为空则错误完成；否则调 requestRoleChoice 推进（角色选择）。"""
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
