"""AERoleExcutor - 角色执行 Flow。

执行链：
  receive_flow_input → requestRoleInformation → receiveRoleInfomation
  → requestOptimizeInput → receiveOptimizeInput → requestRoleChoice → receiveRoleChoice
  → requestWorkflow → receiveWorkflow → flow_receive_complete

role 在 roleChoice 后确认（init 时 self.role=None）。
"""
import logging

from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Roles.Role.AERoleBase import AERoleBase
from Roles.Role.AESubRoleChoice import AESubRoleChoice

logger = logging.getLogger(__name__)


class AERoleExcutor(AERoleBase, AESubRoleChoice):
    """角色执行 Flow：继承 AERoleBase + AESubRoleChoice，由 self.role 决定当前层级行为。

    - expert/workgroup/employee：有下层 → requestRoleSelect（AESubRoleChoice）派发下层角色
    - task：AETaskRole 覆写 requestRoleSelect → requestScripts（脚本执行）
    """

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self._questionType: str = ""
        self.role = None

    def on_flow_start(self, flowInput) -> bool:
        """启动：基类置 input；未启动则错误完成，避免父 flow 等待卡死。"""
        if not super().on_flow_start(flowInput):
            logger.warning("[%s][d=%s] on_flow_start 失败：基类未启动", self.title, self.deepth)
            self.flow_receive_complete(
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
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "角色信息（title/responsibility）生成失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestOptimizeInput()
        return result

    def receiveRoleChoice(self, data: dict) -> bool:
        """接收角色选择：基类设 self.role，成功则推进 requestWorkflow（任务拆解）；失败则以错误完成闭环。"""
        result = super().receiveRoleChoice(data)
        if not result or self.role is None:
            logger.warning("[%s][d=%s] 角色选择失败，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "角色选择失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.print_info()
        self.requestWorkflow()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收角色目标：基类存储后 input.goal 为空则错误完成；否则调 requestRoleChoice 推进（角色选择）。"""
        result = super().receiveOptimizeInput(data)  # AERoleQuestion 存储 input.goal
        if not result or not (self.input.get_goal() if self.input is not None else ""):
            logger.warning("[%s][d=%s] input.goal 为空，以错误完成本 flow 避免卡死",
                           self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "问题优化失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRoleChoice()
        return result

    def receiveWorkflow(self, data: dict) -> bool:
        """接收任务拆解：基类解析+打印任务列表，空则以错误完成闭环；非空则完成本 flow。"""
        result = super().receiveWorkflow(data)
        if not result:
            logger.warning("[%s][d=%s] 任务拆解为空，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "任务拆解为空"},
                AEFlowCompletEvent.error,
            )
            return False
        self.flow_receive_complete(
            {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
             AE_CONTENT: (self.input.get_goal() or self.input.get_content()) if self.input is not None else ""},
        )
        return result
