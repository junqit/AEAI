"""AERoleTarget - 目标分解能力 mixin。

提供 requestTarget / receiveTarget：把 input.goal 按当前工作名称（title）与工作能力
（responsibility）分解为若干落在角色能力范围内的子目标，存入 self.targets
（不派发子 flow、不完成 flow；区别于 AERoleWorkflow 的任务拆解+派发）。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleTargetFunction(AEFunctional):
    """目标分解回包功能性方法名。"""
    receiveTarget = "receiveTarget"


class AERoleTarget(AERole):
    """目标分解能力 mixin：把 input.goal 按 title/responsibility 分解为子目标，存 self.targets。"""

    # 请求 LLM 将 input.goal 按当前角色能力分解为子目标，回包经 receiveTarget 写入
    def requestTarget(self) -> None:
        goal = self.input.get_goal() if self.input is not None else ""
        if not goal:
            logger.warning("[%s][d=%s] 无 input.goal，跳过目标分解", self.title, self.deepth)
            return
        # SYSTEM 放角色身份（title+responsibility，不含铁律），目标分解仅依据工作名称与能力范围
        system_parts = []
        if self.title:
            system_parts.append(f"身份：{self.title}")
        if self.responsibility:
            system_parts.append(f"能力范围：{self.responsibility}")
        messages = []
        if system_parts:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: "".join(system_parts)})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "把下方【目标】按当前工作名称与能力范围分解为若干可执行的子目标。\n"
                "要求：\n"
                "- 每个子目标落在当前角色能力范围内，是达成原目标的一个明确环节；\n"
                "- 子目标之间相互独立、合起来完整覆盖原目标；\n"
                "- 颗粒度适中，避免过度拆解；不得编造、不得偏离原目标。\n"
                "\n"
                "【目标】\n" + goal
            ),
        })
        flow_out = self.generateFlowOutput(AERoleTargetFunction.receiveTarget)
        flow_out.set_llm_out({"targets": [llm_generate("分解出的子目标")]})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    # 接收子目标列表，存入 self.targets；空则返回 False（不闭环）
    def receiveTarget(self, data: dict) -> bool:
        targets = data.get("targets") if isinstance(data, dict) else None
        if targets is None and isinstance(data, str):
            targets = [data] if data.strip() else []
        elif not isinstance(targets, list):
            targets = []
        self.targets = [str(t).strip() for t in targets if str(t).strip()]
        if not self.targets:
            logger.warning("[%s][d=%s] 目标分解为空", self.title, self.deepth)
            return False
        logger.info("[%s][d=%s] 分解出 %d 个子目标：", self.title, self.deepth, len(self.targets))
        for i, t in enumerate(self.targets):
            logger.info("  子目标 %d：%s", i + 1, t)
        return True
