"""
AERoleQuestionOptimize - 问题优化能力 mixin。

提供 requestOptimizeInput / receiveOptimizeInput：将问题优化相关的 LLM 请求方法从 AEFlow
抽出至本 mixin，由 AERoleBase 继承获得（与 AERoleInformation / AERoleChoice 等能力 mixin 同级，位于 Roles 包内）。

requestOptimizeInput 以 role_brief 作为系统提示、以 rolePrompt 作为「针对用户问题的优化指令」，
让 LLM 生成一段「问题优化提示」；receiveOptimizeInput 接收回包并存入 self.roleGoal
（不完成 flow）。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import AEConentRole, AE_ROLE, AE_USER_QUESTION_PREFIX
from Roles.AERoleInfo import AERoleInfo

logger = logging.getLogger(__name__)


class AERoleQuestionOptimizeFunction(AEFunctional):
    """AERoleBase 问题优化回包功能性方法名（继承 AEFunctional 基类）。"""
    receiveOptimizeInput = "receiveOptimizeInput"  # 接收 LLM 基于 title+能力 生成的问题优化提示，传入 map


class AERoleQuestionOptimize(AERoleInfo):
    """问题优化能力 mixin：问题优化相关 LLM 请求方法（requestOptimizeInput / receiveOptimizeInput）。
    roleGoal（优化后的问题）由基类 AERoleInfo 持有。"""

    def requestOptimizeInput(self) -> None:
        """组装并发送 LLM 请求：对用户问题做二次解释与补全缺失，输出「优化后的问题」本身，
        不得直接回答该问题。

        - messages: system(role_brief，含身份与能力) / system(问题优化指令) / user(用户问题，AE_USER_QUESTION_PREFIX 前缀；无问题时退化为 user 指令)
        - out_schema: {AE_CONTENT: 优化后的问题 占位}，由 LLM 填充
        - 走 receiveOptimizeInput：回包后赋值 roleGoal（不完成 flow）

        注：本步骤只做问题优化（二次解释 + 补全缺失），不直接回答；rolePrompt 是作答步骤
        （requestLLMAnswer）的指令，此处不用，避免把「转化为可执行目标/作答」倾向带入问题优化。
        """
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 问题优化指令：二次解释与补全缺失，输出优化后的「问题」本身，严禁直接回答。
        # 不用 rolePrompt——它是作答步骤（requestLLMAnswer）的指令，倾向「转化为可执行目标/作答」，
        # 用在此处会让模型直接回答问题（如罗列能力范围），而非优化问题。
        instruction = (
            f"对{AE_USER_QUESTION_PREFIX}做问题优化：在保持原意的前提下，对用户问题进行二次解释与补全缺失，"
            "重述并补全其中隐含或缺失的信息，使其更清晰、更完整、更易于理解，且契合你的专业能力与约束范围。\n"
            "要求：\n"
            "- 输出必须是「一个问题」（优化后的用户问题本身）；\n"
            "- 严禁直接回答该问题，严禁罗列或描述你的能力范围；\n"
            "- 不得扩展原意、不得改变问题意图。"
        )
        user_question = self.input.parameter.get(AE_CONTENT, "") if self.input is not None else ""
        if len(user_question) > 0:
            # 指令放 system、待优化问题放 user——user 才是模型要处理的内容，
            # 避免 DeepSeek 等模型把 user 指令本身当作待优化问题原样改写
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: instruction})
            messages.append({
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{user_question}",
            })
        else:
            # 无待优化问题：指令作为 user 消息，确保存在 user 轮次
            messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: instruction})
        flow_out = self.generateFlowOutput(AERoleQuestionOptimizeFunction.receiveOptimizeInput)
        flow_out.set_llm_out({AE_CONTENT: llm_generate("优化后的问题")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收 LLM 生成的问题优化提示（不完成 flow，仅存储供后续使用）。

        成功时打印一次完整摘要（title / responsibility / 原始问题 / 优化后的问题 / rolePrompt）。

        Args:
            data: 回包内层 llm_out，形如 {AE_CONTENT: <生成的问题优化提示>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        prompt = data.get(AE_CONTENT) if isinstance(data, dict) else None
        if prompt is None and isinstance(data, str):
            prompt = data
        self.roleGoal = prompt or ""
        logger.info(
            "[%s][d=%s] 优化完成:\n"
            "========================================\n"
            "  role: %s\n  deepth: %s\n  title: %s\n  优化后的问题: %s\n"
            "========================================",
            self.title, self.deepth,
            self.role, self.deepth, self.title, self.roleGoal,
        )
        return True
