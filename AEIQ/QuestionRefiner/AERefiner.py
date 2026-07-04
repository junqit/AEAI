"""
AERefiner - 问题精炼 Flow，继承 AEFlow。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。
"""
from WorkFlows.AEFlow import AEFlow


class AERefiner(AEFlow):
    """问题精炼 Flow：改写用户问题，输出 question。"""

    # 输入结构（LLM 按此填充 question）
    INPUT_SCHEMA = {
        "question": "llm 填写用户的问题",
    }

    def __init__(self, ident: str):
        super().__init__(ident=ident)
        # 职称 / 职责要求
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
        # input_schema：本 flow 的输入结构（父 flow 取作 LLM out_schema）
        self.input_schema = self.INPUT_SCHEMA

    def flow_receive_default(self, out_schema) -> None:
        """status=default：切换到 processing（基类处理状态切换）。"""
        super().flow_receive_default(out_schema)

    def flow_receive_processing(self, out_schema) -> None:
        """status=processing：沿用基类空实现。"""
        super().flow_receive_processing(out_schema)
