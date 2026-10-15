"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议 + AEFlowCompletEvent 事件 + AEFlowDelegateImpl 实现。

Flow 在执行过程中通过该 Delegate 与外部交互：
  1. flow_send_llm_request                发送 AELLMPayload 调用 LLM
  2. receive_flow_input           接收输入（含完成通知）
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
            flow: 待添加的子 flow
        """
        ...

    def flow_send_llm_request(self, payload: 'AELLMPayload') -> None:
        """
        发送 AELLMPayload 结构体调用 LLM（无返回值）。

        Args:
            payload: AELLMPayload 结构体
        """
        ...

    def receive_flow_complete(self, flowOutput: 'AEFlowOutput') -> bool:
        """接收 flow 完成结果（AEFlowOutput）。"""
        ...



class AEFlowDelegateImpl(AEFlowDelegate):
    """AEFlowDelegate 协议方法的实例实现（mixin）。

    提供 flow_send_llm_request / add_flow / receive_flow_input 的实例实现。
    """

    # ==================== 接口方法实现（receive_flow_input / add_flow）====================

    def receive_flow_input(self, flowInput) -> bool:
        """接收输入：ident 匹配自身则处理，匹配子 flow 则转发，其他不处理。

        - ident == self.ident：检查状态顺序，晚于才按状态分发（start/processing）
        - ident 命中 _flows 子 flow：转发给子 flow
        - 其他：打印错误，不处理
        """
        if flowInput.ident == self.ident:
            # 检查状态顺序（int Enum 直接比较），self.status 必须早于 input.state 才可接收
            if self.status.value > flowInput.get_state().value:
                logger.warning(
                    "[d=%s] receive_flow_input 状态不允许：self=%s input=%s，忽略",
                    self.deepth, self.status, flowInput.get_state(),
                )
                return False

            if flowInput.get_state() == AEFlowStatus.start:
                return self.on_flow_start(flowInput)

            if flowInput.get_state() == AEFlowStatus.processing:
                return self.on_flow_processing(flowInput)

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
        """启动 flow：置 input、切到 processing。子类覆写以追加业务逻辑（覆写时调 super().on_flow_start 完成基础置位）。"""
        self.input = flowInput
        self.status = AEFlowStatus.processing
        return True

    def on_flow_processing(self, flowInput) -> bool:
        """processing 阶段：默认暂不处理。子类覆写以处理中间消息。"""
        return False

    def sub_flow_complete(self, flowInput) -> bool:
        """子 flow 完成：所有子 flow 均完成则汇总，否则启动下一个 default 子 flow。"""
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
                from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
                next_flow.receive_flow_input(AEFlowInput(content=flowInput.get_content(), ident=next_flow.ident))
        return True

    def receive_flow_complete(self, flowOutput: 'AEFlowOutput') -> bool:
        """接收 flow 完成通知：按 ident 路由——命中自身则检查全部子流完成→汇总；命中子 flow 则转发。"""
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
                    from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
                    next_flow.receive_flow_input(AEFlowInput(content=flowOutput.outResult or "", ident=next_flow.ident))
            return True

        sub = self._flows.get(flowOutput.ident) if flowOutput.ident else None
        if sub is not None:
            return sub.receive_flow_complete(flowOutput)

        logger.error("[%s][d=%s] receive_flow_complete ident=%s 既非自身也未命中子 flow，忽略",
                     self.title, self.deepth, flowOutput.ident)
        return False

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
        发送 AELLMPayload 调用 LLM（无返回值）。本方法兼发起方与各层上级中继：

        - payload.deepth 未设置（发起方）：当前目标上下文为第 N 级（N=本 flow deepth），请仅回答本级任务；
          置 payload.deepth=N 触发上级逐层追加（串联任务链）。
        - payload.deepth 已设置（上级中继）：第 M 级目标：goal，此目标不作为问题，只是对第 M+1 级目标上下文的约束。
        用当前 flow 的 ident 包装 payload.out_schema，再向上转发（回程按 ident 路由回本 flow）。

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        goal = (self.input.get_goal() if self.input is not None else "")
        if payload.deepth is None:
            # 发起方：当前目标上下文为第 N 级，请仅回答本级任务；置 deepth=N 触发上级逐层追加（串联任务链）
            content = f"当前目标上下文为第 {self.deepth} 级，请仅回答本级任务"
            payload.deepth = self.deepth
        else:
            # 上级中继：本层目标不作为问题，只是对下一级（deepth+1）目标上下文的约束
            content = f"第 {self.deepth} 级目标：{goal}，此目标不作为问题，只是对第 {self.deepth + 1} 级目标上下文的约束"
        payload.messages.insert(0, {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: content})
        payload.out_schema = {
            AE_IDENT: self.ident,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.flow_send_llm_request(payload)

    # ==================== 结果汇总编排 ====================

    def summarize_to_llm(self) -> None:
        """收集所有子 flow 的 outResult 放入 messages，交 LLM 总结形成最终结论。

        汇总编排：summarize_extend_messages（hook）+ 各子 flow outResult_summary（hook）+
        summarize_prompt（hook）。由 sub_flow_complete 在所有子 flow 完成时调用。
        """
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

        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    def summarize_extend_messages(self) -> list:
        """汇总扩展 message（hook）：返回需追加到汇总 messages 头部的额外消息列表。默认空。"""
        return []

    def summarize_prompt(self) -> str:
        """汇总 user 指令（hook）：子类可覆写以定制口吻。"""
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

    def receive_summarize_result(self, data: dict) -> bool:
        """接收 summarize_to_llm 的返回结果，调 flow_complete 完成本 flow。"""
        return self.flow_complete(data)
