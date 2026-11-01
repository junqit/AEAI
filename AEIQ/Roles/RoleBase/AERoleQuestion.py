"""
AERoleQuestion - 目标生成能力 mixin。

提供目标生成的两步 LLM 请求方法：
  requestOptimizeInput → receivePromptTemplate：以 role_brief 作系统提示，生成角色 prompt 模板并存入 rolePrompt；
  _requestGoalFormation → receiveOptimizeInput：综合工作名称/能力范围/prompt 模板，把用户问题做成
  可完成的目标（必须能准确、完整、全面回答用户输入），存入 self.input.goal（不完成 flow）。
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
    receiveOptimizeInput = "receiveOptimizeInput"      # 接收生成的目标，存入 input.goal
    receivePromptTemplate = "receivePromptTemplate"    # 接收角色 prompt 模板，存 rolePrompt 并触发目标生成


class AERoleQuestion(AERole):
    """目标生成能力 mixin：目标生成相关 LLM 请求方法（requestOptimizeInput / receiveOptimizeInput）。
    goal（可完成的目标）由 input 持有（self.input.goal）。"""

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
                "该 prompt 模板将用于后续把用户问题做成可完成的目标，保证能准确、完整、全面回答用户输入。\n"
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

    # 接收角色 prompt 模板，存入 rolePrompt 后触发目标生成（不存 goal，故不推进执行器）
    def receivePromptTemplate(self, data: dict) -> bool:
        template = data.get(AE_CONTENT) if isinstance(data, dict) else None
        if template is None and isinstance(data, str):
            template = data
        self.rolePrompt = template or ""
        self._requestGoalFormation()
        return True

    # 第二步：综合 工作名称/能力范围/prompt 模板 把用户问题做成可完成的目标（必须能准确、完整、全面回答用户输入）
    def _requestGoalFormation(self) -> None:
        user_question = self.input.get_content() if self.input is not None else ""
        if not user_question:
            logger.warning("[%s][d=%s] 无用户问题，跳过目标生成", self.title, self.deepth)
            if self.input is not None:
                self.input.set_goal("")
            return
        # SYSTEM 放角色身份（title+responsibility，不含铁律以避与"不回答"冲突）；prompt 模板作 USER 内数据
        system_parts = []
        if self.title:
            system_parts.append(f"你的身份是：{self.title}")
        if self.responsibility:
            system_parts.append(f"你的能力范围是：{self.responsibility}")
        messages = []
        if system_parts:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: "".join(system_parts)})
        user_parts = [
            "把下方【用户问题】做成一个可完成的目标。",
            "要求：\n"
            "- 必须保证目标能够准确、完整、全面地回答用户输入（必须！）：完成该目标即等价于完整作答用户问题，不得遗漏、不得偏离原意；\n"
            "- 依据身份、能力范围与 prompt 模板体现的方向形成目标，目标须可完成、可执行；\n"
            "- 仅输出目标本身，不回答问题、不解释。",
        ]
        if len(self.rolePrompt) > 0:
            user_parts.append("【prompt 模板】\n" + self.rolePrompt)
        user_parts.append("【用户问题】\n" + user_question)
        messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: "\n\n".join(user_parts)})
        flow_out = self.generateFlowOutput(AERoleQuestionFunction.receiveOptimizeInput)
        flow_out.set_llm_out({AE_CONTENT: llm_generate("可完成的目标")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    # 接收生成的目标，存入 input.goal（不完成 flow；由执行器 receiveOptimizeInput 推进角色选择）
    def receiveOptimizeInput(self, data: dict) -> bool:
        goal = data.get(AE_CONTENT) if isinstance(data, dict) else None
        if goal is None and isinstance(data, str):
            goal = data
        if self.input is not None:
            self.input.set_goal(goal or "")
        return True
