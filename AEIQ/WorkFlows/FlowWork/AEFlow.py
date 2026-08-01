"""
AEFlow - Flow 基类，实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

方法分区：
  - AEFlowInterface 实现：set_delegate / flow_receive_default|processing|complete / nextFlow / send_llm_payload
    （startFlow / addFlow / receive_llm_response / flow_receive_llm 由 AEFlowInterfaceImpl 提供）
  - AEFlowDelegate 实现（继承 AEFlowDelegateImpl 实例方法）：receive_flow_llm_request / receive_add_flow / receive_flow_complete

本类只管工作流流转（路由 / 转发 / 完成判定 / 子 flow 编排）；角色相关信息（title/responsibility/
roleGoal/rolePrompt 及 role_brief/outResult_summary/汇总拼消息）属 Roles.AERoleBase，不在本类。
问题优化由 Roles.AERoleQuestionOptimize 提供；角色信息由 Roles.AERoleInformation 提供（AERoleBase 继承）。
"""
import json
import logging
import uuid
import weakref
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo, AEFlowStatus, AE_IDENT, AE_ANSWER
from .AEFlowDelegate import AEFlowCompletEvent, AEFlowDelegateImpl
from .AEFlowInterface import AEFlowInterfaceImpl
from .AEFlowInput import AEFlowInput
from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from Context.Context.AELLMPayload import AELLMPayload
from Tools.Excutor import AERuntimeExcutor


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface


class AEFlow(AEFlowInfo, AEFlowDelegateImpl, AEFlowInterfaceImpl):
    """Flow 基类，多继承 AEFlowInfo（元信息：ident/input/output/status + generateFlowOutput）/ AEFlowDelegateImpl（delegate 方法）/ AEFlowInterfaceImpl（接口方法 startFlow/addFlow/receive_llm_response）"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        super().__init__(flowOutput=flowOutput, ident=ident, flowInput=flowInput)
        self.delegate: "Optional[AEFlowDelegate]" = None
        self._flows: "Dict[str, AEFlowInterface]" = {}
        self.excutor = AERuntimeExcutor()

    # ==================== AEFlowInterface 实现 ====================

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def registerFunctional(self, method: str) -> str:
        """注册临时功能性方法。funcident 为随机字符串键，method 为方法名字符串。

        Args:
            method: 方法名字符串（如 AEFunctional.flow_receive_*），executor 内部经 method_call 拼 script

        Returns:
            随机生成的 funcident，供写入 out_schema 的 AE_funcationkey 字段
        """
        funcident = uuid.uuid4().hex
        self.excutor.add_temporary(funcident, method, self)
        return funcident

    def flow_receive_default(self, out_schema: "Optional[dict]") -> bool:
        """
        status=default：收到结果数据，置本 flow 状态为 default。子类可覆写做业务处理。

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.default
        return True

    def flow_receive_processing(self, out_schema: "Optional[dict]") -> bool:
        """
        status=processing：收到结果数据，置本 flow 状态为 processing。子类可覆写做业务处理。

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.processing
        return True

    def flow_receive_complete(self, out_schema: "Optional[dict]", event: "AEFlowCompletEvent" = AEFlowCompletEvent.default) -> bool:
        """
        status=complete：收到结果数据，置本 flow 状态为 complete，赋值最终结果，并通过 delegate.receive_flow_complete 通知返回。

        幂等保护：已 complete 的 flow 不再重复置位 / 重复通知 delegate。自身多发汇总时每个
        回包都会回调本方法，若不加判断会向父 flow 重复发送完成事件，触发父层重复汇总
        （"已完成 4/4 仍发多次"的根因）。首次完成即固定 outResult 并通知，后续回包忽略。

        Args:
            out_schema: 完成回包内层 llm_out（含 ident / reply）
            event: 完成事件（AEFlowCompletEvent.default / startFlow / error），透传给 delegate.receive_flow_complete

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        if self.status == AEFlowStatus.complete:
            logger.error(
                "[%s][d=%s] flow_receive_complete 重复完成，忽略（幂等保护）: event=%s outResult=%r",
                type(self).__name__, self.ident, self.deepth, event, out_schema,
            )
            return True
        self.status = AEFlowStatus.complete
        self.outResult = out_schema
        if self.delegate is not None:
            self.delegate.receive_flow_complete(self, event)
        return True

    def nextFlow(self) -> "Optional[AEFlowInterface]":
        """
        获取下一个待执行的子 flow：按 addFlow 顺序首个状态为 default 的子 flow。

        Returns:
            AEFlowInterface: 首个 default 状态的子 flow；均非 default 时返回 None
        """
        for flow in self._flows.values():
            if flow.status == AEFlowStatus.default:
                return flow
        return None

    def send_llm_payload(self, payload: "AELLMPayload") -> None:
        """
        通过 delegate 发送 AELLMPayload（无返回值）。

        校验 delegate 后，用 ident 包装 payload.out_schema 向上转发
        （回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

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

    # ==================== 描述信息 hook（子类覆写提供更丰富描述）====================

    def flow_description(self) -> str:
        """flow 描述信息（hook）：返回 [d=deepth]，子类覆写可追加 role / title。"""
        return f"[d={self.deepth}]"

    # ==================== 结果汇总 hook（编排 summarize_to_llm 在 AEFlowDelegateImpl；子类覆写 summarize_extend_messages / summarize_user_instruction）====================

    def summarize_extend_messages(self) -> list:
        """汇总扩展 message（hook，非私有，可被子类覆写）：返回需追加到汇总 messages 头部的额外消息列表。

        默认返回空列表——flow 内不体现 role 的任何信息；角色上下文等扩展消息由子类
        （如 Roles.AERoleBase）覆写本方法提供。由 AEFlowDelegateImpl.summarize_to_llm 在拼装
        汇总 messages 时调用（messages.extend(self.summarize_extend_messages())）。
        """
        return []

    def summarize_user_instruction(self) -> str:
        """汇总 user 指令（hook，非私有，可被子类覆写）：子类可覆写以定制口吻（如 Chat.AEChat 面向用户的人性化回答）。

        由 AEFlowDelegateImpl.summarize_to_llm 在所有子 flow 完成后调用。
        """
        return (
            "请对以上各子任务的结果进行总结，形成最终结论；"
            "总结时必须保留所有重点信息与关键细节，不得遗漏或弱化要点，也不能为精简而丢掉重要信息；"
            "仅对冗余、重复的内容去重。"
        )

    # ==================== AEFlowDelegate 实现 ====================
