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

    def flow_receive_llm(self, out_schema) -> None:
        """处理路由到本 flow 的 LLM 回复：打印收到的数据，解析 question 存为 outResult。"""
        print(f"[AERefiner:{self.ident}] 收到数据: {out_schema}")
        if isinstance(out_schema, dict):
            refined = out_schema.get("question")
            if refined is not None:
                self.outResult = refined
