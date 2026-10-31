"""
AERoleQuestion - 任务生成能力 mixin。

提供 requestOptimizeInput / receiveOptimizeInput：将任务生成相关的 LLM 请求方法抽出至本 mixin。

requestOptimizeInput 以 role_brief 作为系统提示、以任务生成指令让 LLM 对原始问题或目标生成
一个明确的任务（不可改变原有意思与目标）；receiveOptimizeInput 接收回包并存入 self.input.goal
（不完成 flow）。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleQuestionFunction(AEFunctional):
    """任务生成回包功能性方法名。"""
    receiveOptimizeInput = "receiveOptimizeInput"      # 接收转义后的问题（明确任务），存入 input.goal
    receivePromptTemplate = "receivePromptTemplate"    # 接收角色 prompt 模板，存 rolePrompt 并触发转义


class AERoleQuestion(AERole):
    """任务生成能力 mixin：任务生成相关 LLM 请求方法（requestOptimizeInput / receiveOptimizeInput）。
    goal（明确的任务）由 input 持有（self.input.goal）。"""

    # 第一步：基于工作名称与工作能力生成通用角色 prompt（不含用户问题）
    def requestOptimizeInput(self) -> None:
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "基于当前工作名称与工作能力，生成一个通用的角色 prompt 模板。\n"
                "该 prompt 模板将用于后续对用户问题进行转义，使其更全面、完整、准确。\n"
                "要求：\n"
                "- 仅输出 prompt 模板本身，不含具体问题；\n"
                "- 模板应体现角色能力范围内的上下文、约束与处理方向；\n"
                "- 保持通用性，可适配各类问题。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleQuestionFunction.receivePromptTemplate)
        flow_out.set_llm_out({AE_CONTENT: llm_generate("角色 prompt 模板")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    # 接收角色 prompt 模板，存入 rolePrompt 后触发问题转义（不存 goal，故不推进执行器）
    def receivePromptTemplate(self, data: dict) -> bool:
        template = data.get(AE_CONTENT) if isinstance(data, dict) else None
        if template is None and isinstance(data, str):
            template = data
        self.rolePrompt = template or ""
        self._requestQuestionTranslate()
        return True

    # 第二步：用角色 prompt 模板对用户问题进行转义（保持原意）
    def _requestQuestionTranslate(self) -> None:
        user_question = self.input.get_content() if self.input is not None else ""
        if not user_question:
            logger.warning("[%s][d=%s] 无用户问题，跳过转义", self.title, self.deepth)
            if self.input is not None:
                self.input.set_goal("")
            return
        messages = []
        if len(self.rolePrompt) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: self.rolePrompt})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "用上述角色 prompt 模板对以下用户问题进行转义，使其更全面、完整、准确。\n"
                "要求：\n"
                "- 保持原意准确，不改变问题目标与意图；\n"
                "- 仅输出转义后的问题，不回答问题。"
            ),
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: "原始问题：\n" + user_question,
        })
        flow_out = self.generateFlowOutput(AERoleQuestionFunction.receiveOptimizeInput)
        flow_out.set_llm_out({AE_CONTENT: llm_generate("转义后的问题")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    # 接收转义后的问题（即明确任务），存入 input.goal（不完成 flow；由执行器 receiveOptimizeInput 推进角色选择）
    def receiveOptimizeInput(self, data: dict) -> bool:
        goal = data.get(AE_CONTENT) if isinstance(data, dict) else None
        if goal is None and isinstance(data, str):
            goal = data
        if self.input is not None:
            self.input.set_goal(goal or "")
        return True
