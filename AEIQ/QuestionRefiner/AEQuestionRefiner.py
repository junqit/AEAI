"""
AEQuestionRefiner - 问题精炼器
将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。
"""
import json
from typing import List, Dict, Any, Optional

from Assistant.AERole import AERole


class AEQuestionRefiner:

    ROLE = "Question Refiner"

    SYSTEM_PROMPT = """你是一名问题解释者（Question Refiner）。

职责：
将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。

要求：
1. 保持用户原始意图不变。
2. 不增加用户未明确表达的新需求。
3. 不进行分析、推理或回答问题。
4. 不补充事实信息。
5. 只优化表达方式。
6. 输出应该直接作为后续 AI 的输入。

如果问题已经清晰，则仅做轻微优化。"""

    OUTPUT_SCHEMA = {
        "refined_question": "改写后的问题文本",
    }

    def __init__(self):
        pass

    def build_messages(self, question: str, context: List[Dict[str, str]] = None) -> List[Dict[str, str]]:
        """
        构建发给 LLM 的完整消息列表。

        Args:
            question: 用户原始问题
            context: 可选的历史消息上下文

        Returns:
            完整的 messages 列表
        """
        messages = []

        if context:
            messages.extend(context)

        user_content = self._build_user_prompt(question)
        messages.append({"role": AERole.USER.value, "content": user_content})

        return messages

    def build_system(self) -> str:
        """返回系统提示词"""
        return self.SYSTEM_PROMPT

    def build_output_instruction(self) -> str:
        """返回 LLM 需要输出的结构说明"""
        example = json.dumps(self.OUTPUT_SCHEMA, ensure_ascii=False, indent=2)
        return f"""你必须严格按以下 JSON 结构输出，不要输出任何 JSON 之外的文字：

{example}

其中 refined_question 替换为你改写后的问题。"""

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
            if isinstance(parsed, dict) and "refined_question" in parsed:
                return parsed["refined_question"]
        except json.JSONDecodeError:
            pass
        return None

    def _build_user_prompt(self, question: str) -> str:
        output_instruction = self.build_output_instruction()
        return f"""[用户原始问题]:
{question}

[输出要求]:
{output_instruction}"""
