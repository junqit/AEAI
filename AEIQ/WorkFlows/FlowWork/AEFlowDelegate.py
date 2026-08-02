"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议 + AEFlowCompletEvent 事件 + AEFlowDelegateImpl 实现。

Flow 在执行过程中通过该 Delegate 与外部（如 WorkFlow 运行器 / ContextManager）交互：
  1. receive_flow_llm_request                发送 AELLMPayload 调用 LLM
  2. receive_flow_complete           Flow 完成，按 input_schema 结构返回 map
  3. receive_add_flow      添加下一个待执行的子 flow

任何类只要实现以下方法即视为符合协议，无需继承。

AEFlowDelegateImpl 为协议方法的实例实现（mixin），由 AEFlow 继承获得这些方法，
无需再在 AEFlow 中写转调包装。方法内部以 self 引用所属 flow。

本类管工作流流转（结果路由 / 子 flow 编排 / 完成聚合触发）与结果汇总编排（summarize_to_llm，
非私有，可被子类单独实现）；汇总扩展消息 hook（summarize_extend_messages）与 outResult_summary
属角色信息，由 Roles.AERoleBase 覆写，subflow_summarize_prompt 由 Chat.AEChat 覆写
（receive_flow_result 在所有子 flow 完成时调 self.summarize_to_llm()）。flow 基类不体现 role 信息。
"""
import logging
from enum import Enum
from typing import Protocol, TYPE_CHECKING, runtime_checkable, Optional

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInfo import AEFlowInfo, AE_IDENT, AE_ANSWER, AEFlowStatus
from .AEFlowInput import AEFlowInput
from Context.Context.AELLMPayload import AELLMPayload
from Tools.Excutor.AERuntimeExcutor import AEFunctional

if TYPE_CHECKING:
    from .AEFlowInterface import AEFlowInterface

logger = logging.getLogger(__name__)


class AEFlowCompletEvent(str, Enum):
    """Flow 完成事件（delegate.receive_flow_complete 传入）：区分完成后的后续动作"""
    default = "default"            # 完成回到默认（普通完成）
    startFlow = "startFlow"        # 完成并启动下一个 flow
    error = "error"                # 完成但出现错误


@runtime_checkable
class AEFlowDelegate(Protocol):
    """Flow 委托协议：Flow 内部信息向外流转的出口"""

    def receive_flow_llm_request(self, payload: 'AELLMPayload') -> None:
        """
        发送 AELLMPayload 结构体调用 LLM（无返回值）。

        Args:
            payload: AELLMPayload 结构体
        """
        ...

    def receive_flow_complete(self, result: AEFlowInfo, event: 'AEFlowCompletEvent') -> None:
        """
        Flow 完成通知：result 为完成 flow 实例（AEFlowInfo），event 为完成事件。

        Args:
            result: 完成 flow 实例；其 outResult 为结果数据 dict（含 ident）
            event: 完成事件（AEFlowCompletEvent.default / startFlow）
        """
        ...

    def receive_add_flow(self, flow: 'AEFlowInterface') -> None:
        """
        添加下一个待执行的子 flow。

        Args:
            flow: 待添加的子 flow，须符合 AEFlowInterface 协议
        """
        ...


class AEFlowDelegateImpl(AEFlowDelegate):
    """AEFlowDelegate 协议方法的实例实现（mixin），由 AEFlow 继承获得这些方法。

    显式继承 AEFlowDelegate 协议，声明本类提供 receive_flow_llm_request /
    receive_add_flow / receive_flow_complete 三个协议方法（receive_flow_result 为内部
    控制方法）。方法内以 self 引用所属 flow（ident / _flows / delegate / nextFlow /
    generateFlowOutput / send_llm_payload 等均由 AEFlow 及其基类提供）。
    """

    # ==================== 协议方法实现（AEFlowDelegate）====================

    def receive_add_flow(self, next_flow) -> None:
        """添加下一个待执行的子 flow：将其作为子 flow 加入（addFlow），成为 nextFlow 候选。

        加入后由父 flow 的 receive_flow_result 在适当时机 startFlow 启动（input 取上游结果）。

        Args:
            next_flow: 待添加的子 flow
        """
        self.addFlow(next_flow)

    def receive_flow_llm_request(self, payload: "AELLMPayload") -> None:
        """
        发送 AELLMPayload 调用 LLM（无返回值）。

        AEFlow 自身不持有 LLM 客户端，真实发送由外层 delegate（具体 AEFlowDelegate 实现，
        如 AENetRouteCenter 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident
        包装 payload.out_schema，再向上转发（回程按 ident 路由回本 flow）。

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        payload.out_schema = {
            AE_IDENT: self.ident,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.receive_flow_llm_request(payload)

    def receive_flow_complete(self, result: AEFlowInfo, event: "AEFlowCompletEvent") -> None:
        """
        Flow 完成通知：按 event 区分处理。

        - default：按 result.ident 路由结果数据（ident 命中自身 → receive_flow_result；
          命中子 flow → 转发给该子 flow 的 receive_flow_result）。
        - startFlow：从 subFlows 按 result.ident 取出子 flow 并 startFlow（input 取 result 的 AE_ANSWER）。
        - error：完成但出错，仍按 ident 路由结果推进 flow（与 default 同路径，额外告警），
          避免父 flow 因收不到回包而 all(complete) 永不成立、整条卡死。

        Args:
            result: 完成 flow 实例（AEFlowInfo）；其 outResult 为结果数据 dict（含 ident）
            event: 完成事件（AEFlowCompletEvent.default / startFlow / error）
        """
        out = result.outResult if isinstance(result.outResult, dict) else {}
        ident = out.get(AE_IDENT)
        reply_len = len(out.get(AE_ANSWER, ""))
        logger.info(
            "[%s][d=%s] receive_flow_complete event=%s reply_len=%d",
            self.title, self.deepth, event, reply_len,
        )
        if event == AEFlowCompletEvent.startFlow:
            sub = self._flows.get(ident) if ident is not None else None
            if sub is not None:
                answer = out.get(AE_ANSWER)
                sub.startFlow(AEFlowInput(content=answer or ""))
                return
            logger.warning(
                "[%s][d=%s] startFlow 未命中子 flow",
                self.title, self.deepth,
            )
            return
        if event == AEFlowCompletEvent.error:
            logger.warning(
                "[%s][d=%s] error 事件，按结果路由推进 flow",
                self.title, self.deepth,
            )
        if ident == self.ident:
            self.receive_flow_result(out)
            return
        sub = self._flows.get(ident) if ident is not None else None
        if sub is not None:
            sub.receive_flow_result(out.get(AE_LLM_OUT))
            return
        logger.warning(
            "[%s][d=%s] 既非自身也未命中子 flow，忽略: %r",
            self.title, self.deepth, result,
        )

    # ==================== 完成结果路由与聚合触发 ====================

    def receive_flow_result(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 receive_flow_complete 路由到自身、确认由本 flow 处理的结果数据（纯控制）。

        - 有 default 子 flow：启动下一个 default 子 flow（异步执行）
        - 所有子 flow 均已完成：触发 self.summarize_to_llm() 汇总（默认实现在本类
          AEFlowDelegateImpl；summarize_extend_messages / subflow_summarize_prompt 等 hook 由
          Roles.AERoleBase / Chat.AEChat 覆写）。
        - 否则等待剩余子 flow。

        Args:
            out_schema: 结果数据（含 AE_ANSWER 字段）
        """
        answer = out_schema.get(AE_ANSWER) if isinstance(out_schema, dict) else None
        # 先判断是否全部完成，再 startFlow 下一个子 flow。顺序不可颠倒：
        # 脚本等同步完成的子 flow 会让 startFlow 嵌套触发后续 receive_flow_result；
        # 若先 startFlow 再判断，递归回溯时每层都会重复判断 all(complete)（此时已全完成）
        # 导致重复汇总。先判断、再 startFlow，则只有最后一个子 flow 完成时触发一次。
        if all(f.status == AEFlowStatus.complete for f in self._flows.values()):
            self.summarize_to_llm()
            return

        next_flow = self.nextFlow()
        if next_flow is not None:
            next_flow.startFlow(AEFlowInput(content=answer or ""))

    # ==================== 结果汇总编排（由 AERoleBase 实现，AEFlow 不参与）====================

    def summarize_to_llm(self) -> None:
        """AEFlow 默认：直接完成本 flow 闭环，不做 LLM 汇总。由子类（AERoleBase）覆写为 LLM 汇总。"""
        self.flow_receive_complete(
            {AE_IDENT: self.ident, AE_ANSWER: ""},
            AEFlowCompletEvent.default,
        )
