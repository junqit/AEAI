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
    receiveOptimizeInput = "receiveOptimizeInput"  # 接收 LLM 生成的明确任务，传入 map


class AERoleQuestion(AERole):
    """任务生成能力 mixin：任务生成相关 LLM 请求方法（requestOptimizeInput / receiveOptimizeInput）。
    goal（明确的任务）由 input 持有（self.input.goal）。"""

    def requestOptimizeInput(self) -> None:
        """组装并发送 LLM 请求：对原始问题或目标生成一个明确的任务，不可改变原有意思与目标。

        - messages: system(role_brief，含身份与能力) / system(任务生成指令) / user(原始问题或目标；无时退化为 user 指令)
        - out_schema: {AE_CONTENT: 明确的任务 占位}，由 LLM 填充
        - 走 receiveOptimizeInput：回包后赋值 input.goal（不完成 flow）

        注：本步骤只生成明确任务、不回答；rolePrompt 是作答步骤（requestLLMAnswer）的指令，此处不用。
        """
        messages = []
        # 任务生成指令：本步骤只生成明确任务、不回答（role_brief 的「必须能给出答案」铁律属作答步，此处不用，避免冲突）。
        instruction = (
            "【任务生成】对原始问题或目标生成一个明确的任务，不可改变原有意思与目标："
            "在保持原意与目标不变的前提下，将原始问题或目标转化为清晰、明确、可执行的任务描述。\n"
            "要求：\n"
            "- 输出且仅输出【一个明确的任务】（任务形式，不是回答）；\n"
            "- 严禁回答用户问题、严禁寒暄或任何对话性回复（如「你好，有什么可以帮你的」是回答，禁止）；\n"
            "- 不可改变原有意思与目标。"
        )
        user_question = self.input.get_content() if self.input is not None else ""
        # 指令 + 原始问题或目标拼接为一条 user 消息
        if len(user_question) > 0:
            messages.append({
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: instruction + "\n\n原始问题或目标：\n" + user_question,
            })
        else:
            # 无原始问题或目标：指令作为 user 消息，确保存在 user 轮次
            messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: instruction})
        flow_out = self.generateFlowOutput(AERoleQuestionFunction.receiveOptimizeInput)
        flow_out.set_llm_out({AE_CONTENT: llm_generate("明确的任务")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收 LLM 生成的明确任务，存入 input.goal（不完成 flow、不打印——由 print_info 统一打印）。

        Args:
            data: 回包内层 llm_out，形如 {AE_CONTENT: <生成的明确任务>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        prompt = data.get(AE_CONTENT) if isinstance(data, dict) else None
        if prompt is None and isinstance(data, str):
            prompt = data
        if self.input is not None:
            self.input.set_goal(prompt or "")
        return True
