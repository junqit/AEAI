"""
AEEmployee - 员工 Flow，继承 AERole。

完成单一流水线的工作：承接上游分配的一条流水线，调用 LLM / Tools 执行其各环节，
产出可被上游整合的结构化结果。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Roles.AEBaseRole import AERole

logger = logging.getLogger(__name__)


class AEEmployee(AERole):
    """员工 Flow：完成单一流水线的工作。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "Employee"
        self.responsibility = (
            "完成单一流水线的工作。\n"
            "要求：\n"
            "1. 仅负责本流水线的执行，不跨流水线、不跨维度规划与决策。\n"
            "2. 调用模型或工具完成流水线各环节（检索 / 分析 / 生成 / 转换等）。\n"
            "3. 产出可直接被上游整合的结构化结果。\n"
            "4. 遇到不明确处向上回传，由工作组或专家裁决。"
        )

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，先 requestRoleInfo 生成自身 title/能力，回包 receiveRole 后再执行实际任务。

        Args:
            flowInput: flow 输入数据（content 即工作组下发的子任务）
        """
        if not super().startFlow(flowInput):
            return
        # 先请求 LLM 生成自身工作名称与能力范围（回包走 receiveRole，再发送实际任务）
        self.requestRoleInfo()

    def receiveRole(self, data: dict) -> bool:
        """接收 title/responsibility 后，请求生成问题优化提示（requestOptimizePrompt）。"""
        result = super().receiveRole(data)
        # title/responsibility 生成后，交 LLM 生成问题优化提示（回包走 receiveOptimizePrompt）
        self.requestOptimizePrompt()
        return result
