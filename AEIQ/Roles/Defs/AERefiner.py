"""
AERefiner - 问题精炼 Flow，继承 AERole。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题，再经 AERole.requestRoleSelect
让 LLM 选择解决角色：选人员角色（expert/workgroup/employee/task）则派发 AERoleExcutor（该角色）；
选 llm 则直接作答。角色选择/派发逻辑由 AERole 基类提供，本类仅做问题精炼与触发。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_ANSWER
from Roles.AERoleType import AE_USER_QUESTION_PREFIX
from Roles.AERole import AERole

logger = logging.getLogger(__name__)


class AERefiner(AERole):
    """问题精炼 Flow：改写用户问题，再让 LLM 选择解决角色（逻辑由 AERole 基类提供）。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
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

    def outResult_summary(self) -> str:
        """覆写：以统一前缀（AE_USER_QUESTION_PREFIX）返回 outResult 的回答。"""
        answer = self.outResult.get(AE_ANSWER, "") if isinstance(self.outResult, dict) else ""
        return f"{AE_USER_QUESTION_PREFIX}{answer}"

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题：交基类存入 optimizePromptResult，再请求 LLM 选择解决角色。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <优化后的问题>}；若直接为字符串则视为问题

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        super().receiveOptimizeInput(data)  # 基类提取 AE_ANSWER 存入 optimizePromptResult + 打印摘要
        self.requestRoleSelect()  # 由 AERole 基类提供：未配置 role → 全部角色可选
        return True

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(title) / system(responsibility) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，含 reply 占位，由 LLM 生成精炼后的问题）

        Args:
            flowInput: flow 输入数据（content 即用户原始问题）
        """
        if not super().startFlow(flowInput):
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），忽略", type(self).__name__, self.title, self.deepth)
            return

        self.requestOptimizeInput()
