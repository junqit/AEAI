"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议 + AEFlowCompletEvent 事件 + AEFlowDelegateImpl 实现。

Flow 在执行过程中通过该 Delegate 与外部（如 WorkFlow 运行器 / ContextManager）交互：
  1. flow_send_llm_request                发送 AELLMPayload 调用 LLM
  2. receive_flow_input           接收输入（含完成通知）
  3. add_flow      添加下一个待执行的子 flow

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
from .AEFlowInfo import AEFlowInfo, AE_IDENT, AE_ANSWER
from .AEFlowInput import AEFlowStatus, AEFlowInput, AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload
from Tools.Excutor.AERuntimeExcutor import AEFunctional

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

    def receive_flow_input(self, flowInput: 'AEFlowInput') -> bool:
        """
        接收输入：根据 input.state 分发不同处理。

        - start：启动 flow（置 input、切到 processing），返回 True
        - processing：暂不处理，返回 False
        - complete：收到完成消息，按 input.ident 路由——命中自身则完成，命中子 flow 则转发

        Args:
            flowInput: flow 输入数据（含 content / state / ident）

        Returns:
            bool: True 表示已处理
        """
        ...

    def add_flow(self, flow: 'AEFlowInterface') -> None:
        """
        添加子 flow。

        Args:
            flow: 待添加的子 flow，须符合 AEFlowInterface 协议
        """
        ...

    def flow_send_llm_request(self, payload: 'AELLMPayload') -> None:
        """
        发送 AELLMPayload 结构体调用 LLM（无返回值）。

        Args:
            payload: AELLMPayload 结构体
        """
        ...




class AEFlowDelegateImpl(AEFlowDelegate):
    """AEFlowDelegate 协议方法的实例实现（mixin），由 AEFlow 继承获得这些方法。

    提供 flow_send_llm_request / add_flow / receive_flow_input 的实例实现。
    """

    # ==================== 接口方法实现（receive_flow_input / add_flow）====================

    def receive_flow_input(self, flowInput) -> bool:
        """接收输入：ident 匹配自身则处理，匹配子 flow 则转发，其他不处理。

        - ident == self.ident：检查状态顺序，晚于才按状态分发（start/processing/complete）
        - ident 命中 _flows 子 flow：转发给子 flow
        - 其他：打印错误，不处理
        """
        if flowInput.ident == self.ident:
            # 检查状态顺序（int Enum 直接比较），self.status 必须晚于 input.state
            if self.status.value <= flowInput.state.value:
                logger.warning(
                    "[d=%s] receive_flow_input 状态不允许：self=%s input=%s，忽略",
                    self.deepth, self.status, flowInput.state,
                )
                return False

            if flowInput.state == AEFlowStatus.start:
                return self.on_flow_start(flowInput)

            if flowInput.state == AEFlowStatus.processing:
                return self.on_flow_processing(flowInput)

            if flowInput.state == AEFlowStatus.complete:
                return self.sub_flow_complete(flowInput)

            return False

        sub = self._flows.get(flowInput.ident) if flowInput.ident else None
        if sub is not None:
            return sub.receive_flow_input(flowInput)

        logger.error(
            "[d=%s] receive_flow_input ident=%s 既非自身也未命中子 flow，忽略",
            self.deepth, flowInput.ident,
        )
        return False

    def on_flow_start(self, flowInput) -> bool:
        """启动 flow：置 input、切到 processing。子类覆写以追加业务逻辑。"""
        self.input = flowInput
        self.status = AEFlowStatus.processing
        return True

    def on_flow_processing(self, flowInput) -> bool:
        """processing 阶段：默认暂不处理。子类覆写以处理中间消息。"""
        return False

    def sub_flow_complete(self, flowInput) -> bool:
        """子 flow 完成：所有子 flow 均完成则汇总，否则通知父 flow 等待。"""
        if all(f.status == AEFlowStatus.complete for f in self._flows.values()):
            self.summarize_to_llm()
            return True
        complete_input = AEFlowInput(
            content=flowInput.parameter.get(AE_CONTENT, ""),
            ident=self.ident,
        )
        complete_input.state = AEFlowStatus.complete
        self.delegate.receive_flow_input(complete_input)
        return True

    def add_flow(self, sub_flow) -> None:
        """添加子 flow。

        添加前把 sub_flow.delegate 设置为当前 flow（弱引用）；以 sub_flow.ident 为 key 存入有序 map。
        子 flow 的 deepth 设为当前 flow.deepth + 1。
        """
        sub_flow.set_delegate(self)
        sub_flow.deepth = self.deepth + 1

        logger.info(
            "%s add_flow %s",
            self.flow_description(),
            sub_flow.flow_description(),
        )
        self._flows[sub_flow.ident] = sub_flow

    # ==================== 协议方法实现（AEFlowDelegate）====================

    def flow_send_llm_request(self, payload: "AELLMPayload") -> None:
        """
        发送 AELLMPayload 调用 LLM（无返回值）。

        AEFlow 自身不持有 LLM 客户端，真实发送由外层 delegate（具体 AEFlowDelegate 实现，
        如 AENetRouteCenter 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident
        包装 payload.out_schema，再向上转发（回程按 ident 路由回本 flow）。

        Raises:
            RuntimeError: delegate 未设置时
        """
        payload.out_schema = {
            AE_IDENT: self.ident,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.flow_send_llm_request(payload)

    # ==================== 结果汇总编排（由 AERoleBase 实现，AEFlow 不参与）====================

    def summarize_to_llm(self) -> None:
        """AEFlow 默认：直接完成本 flow 闭环，不做 LLM 汇总。由子类（AERoleBase）覆写为 LLM 汇总。"""
        self.flow_receive_complete(
            {AE_IDENT: self.ident, AE_ANSWER: ""},
            AEFlowCompletEvent.start,
        )
