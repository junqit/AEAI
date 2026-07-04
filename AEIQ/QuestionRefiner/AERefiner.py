"""
AERefiner - 问题精炼 Flow，继承 AEFlow。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。
"""
import logging

from WorkFlows.AEFlow import AEFlow

logger = logging.getLogger(__name__)


class AERefiner(AEFlow):
    """问题精炼 Flow：改写用户问题，输出 question。"""

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

    def flow_receive_default(self, out_schema) -> None:
        """status=default：收到 LLM 生成的 input_schema，交基类切换到 inputSchemed。"""
        logger.info("[AERefiner:%s][%s] 阶段=default 收到 input_schema", self.ident, self.title)
        super().flow_receive_default(out_schema)

    def flow_receive_processing(self, out_schema) -> None:
        """status=processing：收到转换后的输入数据，交基类切换到 complete。"""
        logger.info("[AERefiner:%s][%s] 阶段=processing 收到输入数据", self.ident, self.title)
        super().flow_receive_processing(out_schema)
