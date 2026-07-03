"""
AERefiner - 问题精炼 Flow，继承 AEFlow。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。
（由 AEQuestionRefiner 迁移而来，转为 Flow 节点。）
"""
import json
from typing import Dict, List, Optional

from Assistant.AERole import AERole
from WorkFlows.AEFlow import AEFlow


class AERefiner(AEFlow):
    """问题精炼 Flow：改写用户问题，输出 refined_question。"""

    # 输入结构（LLM 按此填充 question）
    INPUT_SCHEMA = {
        "question": "",
    }

    def __init__(self, ident: str):
        super().__init__(ident=ident)
        # 职称 / 职责要求（迁自 AEQuestionRefiner.ROLE / SYSTEM_PROMPT）
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
        # input_schema：本 flow 的输入结构（父 flow 取作 LLM out_schema，LLM 据此填充 question）
        self.input_schema = self.INPUT_SCHEMA

    def build_system(self) -> str:
        """返回系统提示词（由职称 + 职责要求 组装）"""
        return f"你是一名{self.title}。\n\n职责：\n{self.responsibility}"

    def build_messages(self, question: str, context: List[Dict[str, str]] = None) -> List[Dict[str, str]]:
        """
        构建发给 LLM 的完整消息列表。

        Args:
            question: 用户原始问题
            context: 可选的历史消息上下文

        Returns:
            完整的 messages 列表
        """
        messages: List[Dict[str, str]] = []
        if context:
            messages.extend(context)
        messages.append({"role": AERole.USER.value, "content": self._build_user_prompt(question)})
        return messages

    def build_output_instruction(self) -> str:
        """返回 LLM 需要输出的结构说明"""
        example = json.dumps(self.INPUT_SCHEMA, ensure_ascii=False, indent=2)
        return (
            "你必须严格按以下 JSON 结构输出，不要输出任何 JSON 之外的文字：\n\n"
            f"{example}\n\n"
            "其中 question 替换为你改写后的问题。"
        )

    def parse_response(self, llm_output: str) -> Optional[str]:
        """
        解析 LLM 的输出，提取改写后的问题。

        Args:
            llm_output: LLM 原始输出文本

        Returns:
            改写后的问题，解析失败返回 None
        """
        try:
            parsed = json.loads(llm_output.strip())
            if isinstance(parsed, dict) and "question" in parsed:
                return parsed["question"]
        except json.JSONDecodeError:
            pass
        return None

    def _build_user_prompt(self, question: str) -> str:
        return f"[用户原始问题]:\n{question}\n\n[输出要求]:\n{self.build_output_instruction()}"

    def flow_receive_llm(self, out_schema) -> None:
        """
        处理路由到本 flow 的 LLM 回复：解析 question 并存为 outResult。
        """
        refined = None
        if isinstance(out_schema, dict):
            refined = out_schema.get("question")
        if refined is None and isinstance(out_schema, str):
            refined = self.parse_response(out_schema)
        if refined is not None:
            self.outResult = refined
