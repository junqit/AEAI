"""
AEFlowRolePrompt - AEFlow 的父类：角色描述相关的 LLM 请求方法。

将 requestOptimizePrompt / receiveOptimizePrompt 从 AEFlow 抽出至本父类，
降低 AEFlow.py 体积。本类继承 AEFlowInfo；AEFlow 继承本类。
AEFlowFunctional 等子类模块符号在方法内懒导入以避免循环导入。
"""
import logging

from .AEFlowInfo import AEFlowInfo, AE_ANSWER
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT

logger = logging.getLogger(__name__)


class AEFlowRolePrompt(AEFlowInfo):
    """AEFlow 父类：角色描述相关 LLM 请求方法（requestOptimizePrompt / receiveOptimizePrompt）。"""

    def requestOptimizePrompt(self) -> None:
        """组装并发送 LLM 请求：仅带自身名称(title)与能力(responsibility)，
        让 LLM 据此生成一段「问题优化提示」——该提示用于引导 LLM 对用户输入的问题做进一步优化。

        - messages: system(role_brief，含身份与能力) / user(生成问题优化提示的指令)
        - out_schema: {AE_ANSWER: 问题优化提示 占位}，由 LLM 填充
        - 走 receiveOptimizePrompt：回包后赋值 optimizePromptResult（不完成 flow）

        注：本步仅依据 title + 能力生成提示，不传入用户问题；用户问题留待后续步骤用该提示进一步优化。
        """
        from WorkFlows.AEFlow import AEFlowFunctional  # 懒导入避免循环
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据你的标题与能力，生成一段「问题优化提示」；该提示将用于引导 LLM 对用户输入的问题"
                "做进一步优化（更清晰、更完整、更易于理解）。提示需体现你的专业角色与能力范围，"
                "且不依赖任何具体用户问题，仅给出通用的优化方向与约束。"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveOptimizePrompt)
        flow_out.set_llm_out({AE_ANSWER: llm_generate("问题优化提示，用于引导对用户问题做进一步优化")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveOptimizePrompt(self, data: dict) -> bool:
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
        # 收到提示词后，用其作为输入上下文发起下一步 LLM 请求，得到最终结果
        self.requestOptimizeInputOptimize()
        return True
