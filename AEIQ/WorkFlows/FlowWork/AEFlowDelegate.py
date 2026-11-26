"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议 + AEFlowCompletEvent 事件 + AEFlowDelegateImpl 实现。

Flow 在执行过程中通过该 Delegate 与外部交互：
  1. flow_send_llm_request                发送 AELLMPayload 调用 LLM
  2. on_flow_start              启动 flow（置 input、切 processing）
  3. add_flow      添加下一个待执行的子 flow

任何类只要实现以下方法即视为符合协议，无需继承。

AEFlowDelegateImpl 为协议方法的实例实现（mixin）。方法内部以 self 引用所属 flow。

本类管工作流流转（结果路由 / 子 flow 编排 / 完成聚合触发）；所有子 flow 完成时调 summarize_to_llm
整理子结果完成本 flow（不调 LLM，仅 flow 控制）。
"""
import logging
from enum import Enum
from typing import Protocol, TYPE_CHECKING, runtime_checkable

from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from .AEFlowInfo import AE_IDENT, AE_CONTENT
from .AEFlowInput import AEFlowStatus
from Context.Context.AELLMPayload import AELLMPayload
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
        # goal 为空时用 content 兜底（没优化目标的层，content 即当前层在处理的任务）
        goal = ""
        if self.input is not None:
            goal = self.input.get_target()
        # 前置上下文消息：goal 上下文 + completeIdent 子 flow 的 goal/答案，插到原 messages 前
        prefix_msgs = []
        if payload.deepth is None:
            payload.deepth = self.deepth
            prefix_msgs.append({AE_ROLE: AEConentRole.SYSTEM.value,
                                AE_CONTENT: f"当前目标上下文为第 {self.deepth} 级，请仅回答本级任务"})
        elif goal:
            prefix_msgs.append({AE_ROLE: AEConentRole.SYSTEM.value,
                                AE_CONTENT: f"第 {self.deepth} 级目标：{goal}。此目标不作为问题，只是对第 {self.deepth + 1} 级目标上下文的约束"})
        if prefix_msgs:
            payload.messages = prefix_msgs + payload.messages
        payload.out_schema = {
            AE_IDENT: self.ident,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.flow_send_llm_request(payload)

    # ==================== 结果汇总编排 ====================

    # 所有子 flow 完成时：整理子结果完成本 flow（不调 LLM，仅 flow 控制）
    def summarize_to_llm(self) -> None:
        logger.info(
            "[%s][d=%s] 子 flow 全部完成 %d/%d，整理结果完成本 flow",
            type(self).__name__, self.deepth, len(self._flows), len(self._flows),
        )
        results = []
        for f in self._flows.values():
            r = f.output.outResult or ""
            if r:
                results.append(r)
        self.flow_complete({AE_IDENT: self.ident, AE_CONTENT: "\n".join(results)})

    # 接收汇总结果，调 flow_complete 完成本 flow
    def receive_summarize_result(self, data: dict) -> bool:
        return self.flow_complete(data)
