"""
AEFlow - Flow 基类，实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

方法分区：
  - AEFlowInterface 实现：set_delegate / flow_receive_default|processing|complete / nextFlow / send_llm_payload
    （receive_flow_input / add_flow / receive_llm_response / flow_receive_llm 由 AEFlowInterfaceImpl 提供）
  - AEFlowDelegate 实现（继承 AEFlowDelegateImpl 实例方法）：flow_send_llm_request / add_flow / receive_flow_input

本类只管工作流流转（路由 / 转发 / 完成判定 / 子 flow 编排）；角色相关信息（title/responsibility/
roleGoal/rolePrompt 及 role_brief/outResult_summary/汇总拼消息）属 Roles.AERoleBase，不在本类。
问题优化由 Roles.AERoleQuestionOptimize 提供；角色信息由 Roles.AERoleInformation 提供（AERoleBase 继承）。
"""
import json
import logging
import uuid
import weakref
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo, AE_IDENT, AE_ANSWER
from .AEFlowDelegate import AEFlowCompletEvent, AEFlowDelegateImpl
from .AEFlowInterface import AEFlowInterfaceImpl
from .AEFlowInput import AEFlowStatus, AEFlowInput
from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Context.Context.AELLMPayload import AELLMPayload
from Tools.Excutor import AERuntimeExcutor


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface


class AEFlow(AEFlowInfo, AEFlowDelegateImpl, AEFlowInterfaceImpl):
    """Flow 基类，多继承 AEFlowInfo（元信息：ident/input/output/status + generateFlowOutput）/ AEFlowDelegateImpl（delegate 方法）/ AEFlowInterfaceImpl（接口方法 receive_flow_input/add_flow/receive_llm_response）"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        super().__init__(flowOutput=flowOutput, ident=ident, flowInput=flowInput)
        self.delegate: "Optional[AEFlowDelegate]" = None
        self._flows: "Dict[str, AEFlowInterface]" = {}
        self.excutor = AERuntimeExcutor()

    # ==================== AEFlowInterface 实现 ====================

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def registerFunctional(self, method: AEFunctional) -> str:
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

    def flow_receive_complete(self, out_schema: "Optional[dict]", event: "AEFlowCompletEvent" = AEFlowCompletEvent.start) -> bool:
        """status=complete：置状态、赋值 outResult，经 delegate.receive_flow_input 通知父 flow。"""
        if self.status == AEFlowStatus.complete:
            logger.error(
                "[%s][d=%s] flow_receive_complete 重复完成，忽略（幂等保护）: event=%s outResult=%r",
                type(self).__name__, self.ident, self.deepth, event, out_schema,
            )
            return True
        self.status = AEFlowStatus.complete
        self.outResult = out_schema
        if self.delegate is not None:
            answer = out_schema.get(AE_ANSWER, "") if isinstance(out_schema, dict) else ""
            complete_input = AEFlowInput(content=answer, ident=self.ident)
            complete_input.state = AEFlowStatus.complete
            self.delegate.receive_flow_input(complete_input)
        return True

    def nextFlow(self) -> "Optional[AEFlowInterface]":
        """
        获取下一个待执行的子 flow：按 add_flow 顺序首个状态为 default 的子 flow。

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
        self.delegate.flow_send_llm_request(payload)

    # ==================== 描述信息 hook（子类覆写提供更丰富描述）====================

    def flow_description(self) -> str:
        """flow 描述信息（hook）：返回 [d=deepth]，子类覆写可追加 role / title。"""
        return f"[d={self.deepth}]"

    # ==================== 结果汇总 hook（编排 summarize_to_llm 在 AEFlowDelegateImpl；子类覆写 summarize_extend_messages / subflow_summarize_prompt）====================

    def summarize_extend_messages(self) -> list:
        """汇总扩展 message（hook，非私有，可被子类覆写）：返回需追加到汇总 messages 头部的额外消息列表。

        默认返回空列表——flow 内不体现 role 的任何信息；角色上下文等扩展消息由子类
        （如 Roles.AERoleBase）覆写本方法提供。由 AEFlowDelegateImpl.summarize_to_llm 在拼装
        汇总 messages 时调用（messages.extend(self.summarize_extend_messages())）。
        """
        return []

    def subflow_summarize_prompt(self) -> str:
        """汇总 user 指令（hook，非私有，可被子类覆写）：子类可覆写以定制口吻（如 Chat.AEChat 面向用户的人性化回答）。

        由 AEFlowDelegateImpl.summarize_to_llm 在所有子 flow 完成后调用。
        """
        return (
            "请根据以上所有子任务的结果，整理形成最终结论。\n"
            "要求：\n"
            "- 保留全部信息，不得删除任何内容\n"
            "- 仅对重复、冗余的部分去重\n"
            "- 按逻辑整理，使结论清晰可读"
        )

    # ==================== AEFlowDelegate 实现 ====================
