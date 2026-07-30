"""
AELLMRole - LLM 直接作答角色 Flow，继承 AERole。

与 AERoleExcutor 共用前置优化链路（角色信息 → rolePrompt → 问题优化），区别在于
最后一步不拆解、不执行脚本，而是直接请求 LLM 作答，回包经 flow_receive_complete 完成。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT
from Roles.AERole import AERole
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AELLMRole(AERole):
    """LLM 直接作答角色：经角色信息/问题优化后，请求 LLM 作答，回包完成 flow。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "LLM"
        self.responsibility = "直接接收问题并调用 LLM 作答，不做拆解或脚本执行。"

    def roleDescription(self) -> str:
        """角色描述：返回本角色的职称与职责。"""
        return f"{self.title}：{self.responsibility}"

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，先 requestRoleInformation 走角色信息/问题优化，再直答。"""
        if not super().startFlow(flowInput):
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），忽略",
                           type(self).__name__, self.title, self.deepth)
            return
        self.requestRoleInformation()

    def receiveRolePrompt(self, data: dict) -> bool:
        """接收 rolePrompt 后，请求生成问题优化提示（requestOptimizeInput）。"""
        result = super().receiveRolePrompt(data)
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题：confirm 则暂停；优化失败则错误完成；否则直接请求 LLM 作答。"""
        confirm = data.get("confirm") if isinstance(data, dict) else None
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
        self._request_direct_answer()
        return result

    def _request_direct_answer(self) -> None:
        """请求 LLM 对优化后的问题作答，回包经 flow_receive_complete 完成本 flow。

        - messages: system(role_brief) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(作答指令)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，由 LLM 填充）
        - 回包 funcationkey=flow_receive_complete，LLM 填充 AE_ANSWER 后即完成本 flow
        """
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        question = self.optimizePromptResult or (self.input.content if self.input is not None else "")
        if len(question) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}"})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"请直接回答{AE_USER_QUESTION_PREFIX}",
        })
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
