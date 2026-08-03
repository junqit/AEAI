"""
AERefiner - 问题精炼 Flow，继承 AERoleExcutor。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题，再经 receiveOptimizeInput → requestRoleSelect
让 LLM 选择解决角色（role=None → 全部角色）：选人员角色则派发对应角色 flow；选 llm 则直接作答。
本类仅覆写 receive_flow_input（→ requestOptimizeInput 精炼，跳过 AERoleExcutor 的 requestRoleInformation）
与 outResult_summary；receiveOptimizeInput 沿用 AERoleExcutor（→ requestRoleSelect）。
"""
import logging

from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT, AE_TITLE
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent, AEFlowDelegateImpl
from Roles.AERoleType import AE_USER_QUESTION_PREFIX, AEFlowRole, ROLE_PARAMS
from Roles.Defs.AERoleExcutor import AERoleExcutor

logger = logging.getLogger(__name__)


class AERefiner(AERoleExcutor):
    """问题精炼 Flow：改写用户问题，再让 LLM 选择解决角色（requestRoleSelect）。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        # 职称 / 职责要求
        self.title = "Question Refiner"
        self.responsibility = (
            "将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。\n"
            "要求：\n"
            "1. 保持用户原始意图不变。\n"
            "2. 不增加用户未明确表达的新需求。\n"
            "3. 不进行分析、推理或回答问题。\n"
            "4. 不补充事实信息。\n"
            "5. 只优化表达方式。\n"
            "6. 输出应该直接作为后续 AI 的输入。\n"
            "如果问题已经清晰，则仅做轻微优化。"
        )
        # 入口 refiner 无静态角色，requestRoleSelect 据此选全部角色（覆写 AERoleExcutor 的 self.role=_role()=task）
        self.role = None

    def outResult_summary(self) -> str:
        """覆写：以统一前缀（AE_USER_QUESTION_PREFIX）返回 outResult 的回答。"""
        answer = self.outResult.get(AE_CONTENT, "") if isinstance(self.outResult, dict) else ""
        return f"{AE_USER_QUESTION_PREFIX}{answer}"

    def receiveRoleSelect(self, data: dict) -> bool:
        """覆写：按 role 创建兄弟 flow 加入 delegate，自身完成（delegate 编排全部兄弟 flow）。"""
        workflows = data.get("workflows") if isinstance(data, dict) else None
        if workflows is None and isinstance(data, str):
            workflows = [workflows] if workflows.strip() else []
        elif not isinstance(workflows, list):
            workflows = []
        delegate_ident = self.delegate.ident
        if not workflows:
            logger.warning("[%s][d=%s] 返回空工作流，以错误完成闭环", self.title, self.deepth)
            self.flow_receive_complete({AE_IDENT: delegate_ident, AE_CONTENT: "未返回可执行工作流"}, AEFlowCompletEvent.error)
            return True
        created = self._create_role_flows(workflows, is_subflow=False)
        if created == 0:
            logger.warning("[%s][d=%s] 全部工作流 role 非法被跳过，以错误完成闭环", self.title, self.deepth)
            self.flow_receive_complete({AE_IDENT: delegate_ident, AE_CONTENT: "全部工作流 role 非法被跳过"}, AEFlowCompletEvent.error)
            return True
        logger.info("[%s][d=%s] 创建 %d 个兄弟 flow，自身完成", self.title, self.deepth, created)
        self.flow_receive_complete({AE_IDENT: delegate_ident, AE_CONTENT: self.roleGoal}, AEFlowCompletEvent.start)
        return True

    def on_flow_start(self, flowInput) -> bool:
        """启动：跳过 AERoleExcutor.on_flow_start（其会 requestRoleInformation），直接走 requestOptimizeInput。"""
        if not AEFlowDelegateImpl.on_flow_start(self, flowInput):
            logger.warning("[%s][d=%s] on_flow_start 失败：基类未启动", self.title, self.deepth)
            return False
        self.requestOptimizeInput()
        return True
