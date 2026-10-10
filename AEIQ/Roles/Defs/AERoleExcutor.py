"""
AERoleExcutor - 角色执行 Flow，继承 AERoleBase + AERoleChoice（角色选择能力）。

能力来源：
  - AERoleBase：角色基类（角色信息 / 问题优化 / role_brief / param_info / _role）
  - AERoleChoice：角色选择（requestRoleSelect / receiveRoleSelect）
  - 本类：角色目标就绪后的推进（requestRoleSelect hook）

执行链：
  receive_flow_input → requestRoleInformation → receiveRoleInfomation → requestRolePrompt
  → receiveRolePrompt → requestOptimizeInput → receiveOptimizeInput → requestRoleSelect
    └─ 默认：requestRoleSelect 派发对应角色 subFlow（task 子类覆写为 requestScripts）

AERoleExcutor 为角色执行基类，task 执行能力（Script Generator）由 AETaskRole 提供；
expert/workgroup/employee 子类（AEExpertRole 等）继承本类，_role() 决定当前层级。
"""
import logging

from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
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
        成功则推进 requestRolePrompt；失败则以错误完成本 flow 闭环避免卡死，并返回 False 如实反映失败。"""
        result = super().receiveRoleInfomation(data)
        if not result or not self.title or not self.responsibility:
            logger.warning("[%s][d=%s] title 或 responsibility 为空，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "角色信息（title/responsibility）生成失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRolePrompt()
        return result

    def receiveRolePrompt(self, data: dict) -> bool:
        """接收 rolePrompt：判断基类处理结果决定下一步（闭环 / 推进）。
        基类校验 map 并存储 rolePrompt，成功返回 True；失败（非 map 或为空）返回 False（基类不闭环）。
        成功则推进 requestOptimizeInput；失败则以错误完成本 flow 闭环避免卡死，并返回 False。"""
        result = super().receiveRolePrompt(data)
        if not result or not self.rolePrompt:
            logger.warning("[%s][d=%s] rolePrompt 为空或回包非 map，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "rolePrompt 生成失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收角色目标：基类存储后 input.goal 为空则错误完成；否则调 requestRoleSelect 推进。"""
        result = super().receiveOptimizeInput(data)  # AERoleQuestionOptimize 存储 input.goal
        if not result or not (self.input.get_goal() if self.input is not None else ""):
            logger.warning("[%s][d=%s] input.goal 为空，以错误完成本 flow 避免卡死",
                           self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "问题优化失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRoleSelect()
        return result
