"""
AERoleQuestionOptimize - 问题优化能力 mixin。

提供 requestOptimizeInput / receiveOptimizeInput：将问题优化相关的 LLM 请求方法从 AEFlow
抽出至本 mixin，由 AERoleBase 继承获得（与 AERoleInformation / AERoleChoice 等能力 mixin 同级，位于 Roles 包内）。

requestOptimizeInput 以 role_brief 作为系统提示、以 rolePrompt 作为「针对用户问题的优化指令」，
让 LLM 生成一段「问题优化提示」；receiveOptimizeInput 接收回包并存入 self.roleGoal
（不完成 flow）。
"""
import logging

from WorkFlows.AEFlowInfo import AE_ANSWER
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import AEConentRole, AE_ROLE, AE_CONTENT, AE_USER_QUESTION_PREFIX
from Roles.AERoleInfo import AERoleInfo

logger = logging.getLogger(__name__)


class AERoleQuestionOptimizeFunction(AEFunctional):
    """AERoleBase 问题优化回包功能性方法名（继承 AEFunctional 基类）。"""
    receiveOptimizeInput = "receiveOptimizeInput"  # 接收 LLM 基于 title+能力 生成的问题优化提示，传入 map


class AERoleQuestionOptimize(AERoleInfo):
    """问题优化能力 mixin：问题优化相关 LLM 请求方法（requestOptimizeInput / receiveOptimizeInput）。
    roleGoal（优化后的问题）由基类 AERoleInfo 持有。"""

    def requestOptimizeInput(self) -> None:
        """组装并发送 LLM 请求：以 role_brief 作为系统提示，以 rolePrompt 作为「提的问题」
        （针对 AE_USER_QUESTION_PREFIX 的优化指令），让 LLM 据此生成一段「问题优化提示」。

        - messages: system(role_brief，含身份与能力) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(rolePrompt 作为针对用户问题的提问指令；为空时回退默认指令)
        - out_schema: {AE_ANSWER: 问题优化提示 占位}，由 LLM 填充
        - 走 receiveOptimizeInput：回包后赋值 roleGoal（不完成 flow）

        注：rolePrompt 由 requestRoleInformation 一并生成，是本角色针对用户问题（AE_USER_QUESTION_PREFIX）
        所提的提问/优化指令；未生成 rolePrompt 的 flow（如 AERefiner）回退到默认指令。
        """
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 用户问题以统一前缀（AE_USER_QUESTION_PREFIX）单独作为 system 消息传入
        user_question = self.input.content if self.input is not None else ""
        if len(user_question) > 0:
            messages.append({
                AE_ROLE: AEConentRole.SYSTEM.value,
                AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{user_question}",
            })
        # rolePrompt 作为针对 AE_USER_QUESTION_PREFIX 的提问指令；为空时回退默认指令
        default_instruction = (
            f"请根据你的职称与能力，对{AE_USER_QUESTION_PREFIX}做优化，不可扩展、不可改变原意思"
            "（更清晰、更完整、更易于理解），使问题更契合你的专业能力与约束范围。"
            "体现你的专业角色，不得超出你的能力与职责边界。"
        )
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: self.rolePrompt or default_instruction,
        })
        flow_out = self.generateFlowOutput(AERoleQuestionOptimizeFunction.receiveOptimizeInput)
        flow_out.set_llm_out({AE_ANSWER: llm_generate("优化后的问题")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收 LLM 生成的问题优化提示（不完成 flow，仅存储供后续使用）。

        成功时打印一次完整摘要（title / responsibility / 原始问题 / 优化后的问题 / rolePrompt）。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <生成的问题优化提示>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        prompt = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if prompt is None and isinstance(data, str):
            prompt = data
        self.roleGoal = prompt or ""
        original = self.input.content if self.input is not None else ""
        logger.info(
            "[%s][%s][d=%s] 优化完成:\n"
            "========================================\n"
            "  title: %s\n  responsibility: %s\n  原始问题: %s\n  优化后的问题: %s\n  rolePrompt: %s\n"
            "========================================",
            type(self).__name__, self.title, self.deepth,
            self.title, self.responsibility, original, self.roleGoal, self.rolePrompt,
        )
        return True
