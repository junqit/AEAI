"""AEIQFlow - AEIQ 项目 Flow 基类，继承 AEFlow，重写 summarize_to_llm 进行 LLM 汇总。"""
import logging

from WorkFlows.FlowWork.AEFlow import AEFlow
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from WorkFlows.FlowWork.AEFlowOutput import AE_LLM_OUT
from Context.Context.AELLMPayload import AELLMPayload
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import AEConentRole, AE_ROLE

logger = logging.getLogger(__name__)


class AEIQFlow(AEFlow):
    """AEIQ Flow 基类：重写 summarize_to_llm，收集子 flow 结果交 LLM 汇总。"""

    def summarize_to_llm(self) -> None:
        """收集所有子 flow 的 outResult 放入 messages，交 LLM 总结形成最终结论。

        汇总编排：summarize_extend_messages（hook）+ 各子 flow outResult_summary（hook）+
        subflow_summarize_prompt（hook）。由 receive_flow_result 在所有子 flow 完成时调用。
        """
        logger.info(
            "[%s][d=%s] summarize_to_llm: 子 flow 全部完成 %d/%d，发送总结请求",
            type(self).__name__, self.deepth, len(self._flows), len(self._flows),
        )
        flow_out = self.generateFlowOutput(AEFunctional.flow_receive_complete)
        messages = []
        messages.extend(self.summarize_extend_messages())
        for f in self._flows.values():
            if f.output.outResult:
                try:
                    summary = f.outResult_summary()
                    messages.append({
                        AE_ROLE: AEConentRole.ASSISTANT.value,
                        AE_CONTENT: summary,
                    })
                except Exception as e:
                    logger.error("[%s][d=%s] summarize 子 flow outResult_summary 异常: %s", type(self).__name__, self.deepth, e, exc_info=True)
            else:
                logger.warning("[%s][d=%s] summarize 子 flow output.outResult 为空, 跳过, status=%s", type(self).__name__, self.deepth, f.status)
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: self.subflow_summarize_prompt(),
        })

        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
