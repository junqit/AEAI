"""
AEFlowOptimizeInput - AEFlow 的父类：问题优化相关的 LLM 请求方法。

将 requestOptimizeInput / receiveOptimizeInput 从 AEFlow 抽出至本父类，
降低 AEFlow.py 体积。本类继承 AEFlowInfo；AEFlow 继承本类。
AEFlowFunctional 等子类模块符号在方法内懒导入以避免循环导入。
"""
import logging

from .AEFlowInfo import AEFlowInfo, AE_ANSWER
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT, AE_USER_QUESTION_PREFIX

logger = logging.getLogger(__name__)


class AEFlowOptimizeInput(AEFlowInfo):
    """AEFlow 父类：问题优化相关 LLM 请求方法（requestOptimizeInput / receiveOptimizeInput）。"""

    def requestOptimizeInput(self) -> None:
        """组装并发送 LLM 请求：仅带自身名称(title)与能力(responsibility)，
        让 LLM 据此生成一段「问题优化提示」——该提示用于引导 LLM 对用户输入的问题做进一步优化。

        - messages: system(role_brief，含身份与能力) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(优化与扩展指令)
        - out_schema: {AE_ANSWER: 问题优化提示 占位}，由 LLM 填充
        - 走 receiveOptimizeInput：回包后赋值 optimizePromptResult（不完成 flow）

        注：本步依据 title + 能力，并以单独 system 消息（带 AE_USER_QUESTION_PREFIX 前缀）传入用户问题，
        生成更贴切的「问题优化提示」；该提示留待后续步骤用于进一步优化。
        """
        from WorkFlows.AEFlow import AEFlowFunctional  # 懒导入避免循环
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
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请根据你的职称与能力，对{AE_USER_QUESTION_PREFIX}做进一步优化与扩展"
                "（更清晰、更完整、更易于理解），使问题更契合你的专业能力与约束范围。"
                "优化与扩展需体现你的专业角色，不得超出你的能力与职责边界。"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveOptimizeInput)
        flow_out.set_llm_out({AE_ANSWER: llm_generate("优化后的问题")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收 LLM 生成的问题优化提示（不完成 flow，仅存储供后续使用）。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <生成的问题优化提示>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        prompt = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if prompt is None and isinstance(data, str):
            prompt = data
        self.optimizePromptResult = prompt or ""
        logger.info(
            "[AEFlow:%s][%s] 收到问题优化提示:\n%s",
            self.ident, self.title, self.optimizePromptResult,
        )
        return True
