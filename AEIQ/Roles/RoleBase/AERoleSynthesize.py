"""AERoleSynthesize - 综合汇总能力 mixin（收敛链 synthesize 阶段）。

收集子任务结果与背景信息，汇总成连贯候选答案，写入 flow_context.synthesis（中间流程结论，非最终 output）。
作为 mixin 混入 AERoleBase，回包 receive_synthesize 落在宿主实例上（AEFlow 回包按方法名派发）。
完成后续由 Orchestrator 覆写 receive_synthesize 调 super 后推进 _orchestrate。
"""
import logging

from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleSynthesizeFunction(AEFunctional):
    """综合汇总回包功能性方法名。"""
    receive_synthesize = "receive_synthesize"


class AERoleSynthesize(AERole):
    """综合汇总能力 mixin：子任务结果 + 背景信息 → 连贯候选答案（中间结论，写入 flow_context.synthesis）。"""

    # synthesize 动作：校验后请求汇总（无子结果与背景则回退决策）
    def do_synthesize(self) -> None:
        if not self.flow_context.has_sub_task_results() and not self.flow_context.has_background():
            logger.info("[%s][d=%s] synthesize 无子结果与背景，回退决策（建议 answer）",
                        self.title, self.deepth)
            self.flow_context.add_error("synthesize 无可汇总内容")
            self._orchestrate()
            return
        self.requestSynthesize()

    # 综合子任务结果与背景，请求 LLM 汇总成连贯候选答案
    def requestSynthesize(self) -> None:
        sub_tasks = self.flow_context.sub_task_results
        messages = []
        role_brief = self.role_brief()
        if role_brief:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        sub_text = "\n".join(f"- 目标：{t.get('goal', '')}\n  结论：{t.get('result', '')}"
                             for t in sub_tasks) if sub_tasks else "（无）"
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"原始问题：{self.input.get_content() if self.input is not None else ''}\n"
                f"优化目标：{self.input.get_goal() if self.input is not None else ''}\n"
                f"背景信息：{self.flow_context.background or '（无）'}\n"
                f"子任务结果：\n{sub_text}\n\n"
                f"请综合以上所有信息，给出完整、连贯、直接回答原始问题的候选答案。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleSynthesizeFunction.receive_synthesize)
        flow_out.set_llm_out({
            "synthesis": llm_generate("综合所有子任务结果与背景信息，给出完整连贯、直接回答原始问题的候选答案"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.5)
        self.flow_send_llm_request(payload)

    # 接收候选答案，写入 flow_context.synthesis（中间结论）；非空返回 True，否则 False（不闭环）
    def receive_synthesize(self, data: dict) -> bool:
        synthesis = ""
        if isinstance(data, dict):
            synthesis = str(data.get("synthesis", "") or "").strip()
        elif isinstance(data, str):
            synthesis = data.strip()
        if synthesis:
            self.flow_context.set_synthesis(synthesis)
            return True
        return False
