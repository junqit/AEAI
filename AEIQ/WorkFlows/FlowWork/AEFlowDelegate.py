"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议 + AEFlowCompletEvent 事件 + AEFlowDelegateImpl 实现。

Flow 在执行过程中通过该 Delegate 与外部交互：
  1. flow_send_llm_request                发送 AELLMPayload 调用 LLM
  2. on_flow_start              启动 flow（置 input、切 processing）
  3. add_flow      添加下一个待执行的子 flow

任何类只要实现以下方法即视为符合协议，无需继承。

AEFlowDelegateImpl 为协议方法的实例实现（mixin）。方法内部以 self 引用所属 flow。

本类管工作流流转（结果路由 / 子 flow 编排 / 完成聚合触发）与结果汇总编排（summarize_to_llm，
非私有，可被子类单独实现）；汇总扩展消息 hook（summarize_extend_messages）与 outResult_summary
为 hook，可被子类覆写（receive_flow_result 在所有子 flow 完成时调 self.summarize_to_llm()）。
"""
import logging
from enum import Enum
from typing import Protocol, TYPE_CHECKING, runtime_checkable

from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from .AEFlowInfo import AE_IDENT, AE_CONTENT
from .AEFlowInput import AEFlowStatus, AEFlowInput, AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE

if TYPE_CHECKING:
    from .AEFlowInterface import AEFlowInterface

logger = logging.getLogger(__name__)


class AEFlowCompletEvent(str, Enum):
    """Flow 完成事件（delegate.receive_flow_input 传入）：区分完成后的后续动作"""
    start = "start"            # 完成回到默认（普通完成）
    receive_flow_input = "receive_flow_input"        # 完成并启动下一个 flow
    error = "error"                # 完成但出现错误


@runtime_checkable
class AEFlowDelegate(Protocol):
    """Flow 委托协议：Flow 内部信息向外流转的出口"""

    # 添加子 flow
    def add_flow(self, flow: 'AEFlowInterface') -> None:
        ...

    # 发送 AELLMPayload 调用 LLM（无返回值）
    def flow_send_llm_request(self, payload: 'AELLMPayload') -> None:
        ...

    # 接收 flow 完成结果
    def receive_flow_complete(self, flowOutput: 'AEFlowOutput') -> bool:
        ...



class AEFlowDelegateImpl(AEFlowDelegate):
    """AEFlowDelegate 协议方法的实例实现（mixin）。

    提供 flow_send_llm_request / add_flow / on_flow_start 的实例实现。
    """

    # ==================== 接口方法实现（add_flow）====================

    # 启动 flow：切到 processing；flowInput 非空时置 input
    def on_flow_start(self, flowInput=None) -> bool:
        self.status = AEFlowStatus.processing
        if flowInput is not None:
            self.input = flowInput
        return True

    # processing 阶段默认暂不处理，子类覆写
    def on_flow_processing(self, flowInput) -> bool:
        return False

    # 接收 flow 完成通知，按 ident 路由
    def receive_flow_complete(self, flowOutput: 'AEFlowOutput') -> bool:
        if flowOutput.ident == self.ident:
            # 完成回调命中自身：若设了 completeIdent，优先调用其注册方法（funcident）；否则走默认汇总/推进
            if self.completeIdent:
                ident = self.completeIdent
                self.completeIdent = ""  # 一次性：触发后清除，避免后续子 flow 完成重复触发
                logger.info("[%s][d=%s] 完成回调命中自身，调用 completeIdent=%s 注册方法",
                            self.title, self.deepth, ident)
                return self.excutor.exec(ident, flowOutput)
            if not self._flows:
                return True
            if all(f.status == AEFlowStatus.complete for f in self._flows.values()):
                self.summarize_to_llm()
            else:
                logger.info("[%s][d=%s] 子 flow 未全部完成: %d/%d",
                            self.title, self.deepth,
                            sum(1 for f in self._flows.values() if f.status == AEFlowStatus.complete),
                            len(self._flows))
                next_flow = self.nextFlow()
                if next_flow is not None:
                    next_flow.on_flow_start()
            return True

        sub = self._flows.get(flowOutput.ident) if flowOutput.ident else None
        if sub is not None:
            return sub.receive_flow_complete(flowOutput)

        logger.error("[%s][d=%s] receive_flow_complete ident=%s 既非自身也未命中子 flow，忽略",
                     self.title, self.deepth, flowOutput.ident)
        return False

    # 添加子 flow：设 delegate、存入 _flows、设 deepth
    def add_flow(self, sub_flow) -> None:
        sub_flow.set_delegate(self)
        sub_flow.deepth = self.deepth + 1

        logger.info(
            "%s add_flow %s",
            self.flow_description(),
            sub_flow.flow_description(),
        )
        self._flows[sub_flow.ident] = sub_flow

    # ==================== 协议方法实现（AEFlowDelegate）====================

    # 发送 AELLMPayload 调用 LLM；发起方置 deepth 触发上级串联，用 ident 包装 out_schema 向上转发
    def flow_send_llm_request(self, payload: "AELLMPayload") -> None:
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # goal 为空时用 content 兜底（Orchestrator 可能跳过 optimize_goal，content 即当前层在处理的任务）
        goal = (self.input.get_goal() if self.input is not None else "") or \
               (self.input.get_content() if self.input is not None else "")
        if payload.deepth is None:
            content = f"当前目标上下文为第 {self.deepth} 级，请仅回答本级任务"
            payload.deepth = self.deepth
        else:
            if goal:
                content = f"第 {self.deepth} 级目标：{goal}，此目标不作为问题，只是对第 {self.deepth + 1} 级目标上下文的约束"
            else:
                content = ""
        if content:
            payload.messages.insert(0, {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: content})
        # 追加 completeIdent 非空的子 flow 的 goal 与答案作为上下文
        ctx_msgs = []
        for sub in self._flows.values():
            if not sub.completeIdent:
                continue
            sub_input = getattr(sub, "input", None)
            sub_output = getattr(sub, "output", None)
            sub_goal = sub_input.get_goal() if sub_input is not None else ""
            sub_answer = sub_output.outResult if sub_output is not None else ""
            if sub_goal or sub_answer:
                ctx_msgs.append({
                    AE_ROLE: AEConentRole.ASSISTANT.value,
                    AE_CONTENT: f"目标：{sub_goal}\n答案：{sub_answer}",
                })
        if ctx_msgs:
            payload.messages[1:1] = ctx_msgs
        payload.out_schema = {
            AE_IDENT: self.ident,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.flow_send_llm_request(payload)

    # ==================== 结果汇总编排 ====================

    # 收集所有子 flow 的 outResult 交 LLM 总结，所有子 flow 完成时调用
    def summarize_to_llm(self) -> None:
        logger.info(
            "[%s][d=%s] summarize_to_llm: 子 flow 全部完成 %d/%d，发送总结请求",
            type(self).__name__, self.deepth, len(self._flows), len(self._flows),
        )
        flow_out = self.generateFlowOutput(AEFunctional.receive_summarize_result)
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
            AE_CONTENT: self.summarize_prompt(),
        })

        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.5)
        self.flow_send_llm_request(payload)

    # 汇总扩展 message hook，默认空
    def summarize_extend_messages(self) -> list:
        return []

    # 汇总 user 指令 hook，子类可覆写
    def summarize_prompt(self) -> str:
        goal = (self.input.get_goal() or self.input.get_content()) if self.input is not None else ""
        prompt = "以上是各子任务的执行结果与结论。请综合全部子任务的结果，输出一份完整的最终结论。"
        if goal:
            prompt += f"\n原始问题/目标：{goal}\n结论须针对该问题/目标作答。"
        prompt += (
            "\n要求：\n"
            "- 必须涵盖上述每一个子任务的结果，不得遗漏任何一个；\n"
            "- 对内容相同或重复的结论合并为一项，不得逐条复制重复内容；\n"
            "- 按逻辑顺序组织（如：先结论后依据、先总体后细节，或按子任务顺序），使读者能快速理解；\n"
            "- 仅输出综合结论本身，不得输出过程说明、分析步骤或额外解释。"
        )
        return prompt

    # 接收汇总结果，调 flow_complete 完成本 flow
    def receive_summarize_result(self, data: dict) -> bool:
        return self.flow_complete(data)
