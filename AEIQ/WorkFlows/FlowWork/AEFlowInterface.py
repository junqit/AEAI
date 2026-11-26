"""
AEFlowInterface - Flow 接口协议 + AEFlowInterfaceImpl 实例实现（mixin），同文件组织。

- AEFlowInterface（Protocol）：声明所有 Flow 需遵循的接口（ident / status / delegate / receive_llm_response）。
- AEFlowInterfaceImpl（mixin）：提供 receive_llm_response / flow_receive_llm / send_llm_request
  的实例实现。
"""
import logging
from typing import Protocol, runtime_checkable, TYPE_CHECKING, Optional

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInput import AEFlowStatus
from .AEFlowInfo import AE_IDENT, AE_CONTENT, AE_funcationkey
from .AEFlowDelegate import AEFlowCompletEvent

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate

logger = logging.getLogger(__name__)


@runtime_checkable
class AEFlowInterface(Protocol):
    """Flow 接口协议，所有 flow 需遵循此协议进行实现"""

    ident: str
    status: 'AEFlowStatus'
    delegate: 'AEFlowDelegate'

    # 接收输入数据 map，内部解析处理
    def receive_llm_response(self, data: dict) -> None:
        ...

    # 完成本 flow：置 complete、赋值 outResult、通知父 flow
    def flow_complete(self, data: dict) -> bool:
        ...

    # 更新 flow 输入（不启动、不改状态）
    def update_flow_input(self, flowInput) -> bool:
        ...


class AEFlowInterfaceImpl(AEFlowInterface):
    """AEFlowInterfaceImpl 协议方法实现（mixin）。

    提供 receive_llm_response / flow_receive_llm / send_llm_request 的实例实现。
    """

    # 接收输入数据，按 ident 路由：命中自身交 flow_receive_llm，命中子 flow 转发
    def receive_llm_response(self, data: dict) -> None:
        if not isinstance(data, dict):
            logger.error(
                "[d=%s] 收到的数据非 map，无法解析，以错误完成本 flow 闭环: %r",
                self.deepth, data,
            )
            self.flow_complete({AE_IDENT: self.ident, AE_CONTENT: "LLM 回包非 map，无法解析"}, AEFlowCompletEvent.error)
            return

        ident = data.get(AE_IDENT)

        if ident == self.ident:
            self.flow_receive_llm(data)
            return

        sub = self._flows.get(ident) if ident is not None else None
        if sub is not None:
            sub.receive_llm_response(data.get(AE_LLM_OUT))
            return

        logger.error(
            "[d=%s] 无法命中（既非自身也未匹配子 flow），忽略: %r",
            self.deepth, data,
        )

    # 按 out_schema 内 funcationkey 从 excutor 取脚本执行
    def flow_receive_llm(self, out_schema: "Optional[dict]") -> None:
        if not isinstance(out_schema, dict):
            logger.error(
                "[d=%s] out_schema 非 map，以错误完成本 flow 避免卡死: %r",
                self.deepth, out_schema,
            )
            self.flow_complete({AE_IDENT: self.ident, AE_CONTENT: "LLM 回包非 map，无法处理"}, AEFlowCompletEvent.error)
            return
        command = out_schema.get(AE_funcationkey)
        inner = out_schema.get(AE_LLM_OUT)
        if not self.excutor.contains(command):
            logger.error(
                "[d=%s] out_schema 内 funcationkey=%r 无效或缺失，以错误完成本 flow 避免卡死: %r",
                self.deepth, command, out_schema,
            )
            self.flow_complete({AE_IDENT: self.ident, AE_CONTENT: "LLM 回包 funcationkey 无效，无法路由处理"}, AEFlowCompletEvent.error)
            return
        self.excutor.exec(command, inner)

    # 置 complete、赋值 outResult，通知父 flow
    def flow_complete(self, out_schema: "Optional[dict]", event: "AEFlowCompletEvent" = AEFlowCompletEvent.start) -> bool:
        if self.status == AEFlowStatus.complete:
            logger.error(
                "[%s][d=%s] flow_complete 重复完成，忽略（幂等保护）: event=%s out_schema=%r",
                type(self).__name__, self.deepth, event, out_schema,
            )
            return True
        self.status = AEFlowStatus.complete
        answer = out_schema.get(AE_CONTENT, "") if isinstance(out_schema, dict) else ""
        self.output.outResult = answer
        self.output.ident = self.ident
        if self.delegate is not None:
            self.delegate.receive_flow_complete(self.output)
        return True

    # 更新 input（不启动、不改状态）
    def update_flow_input(self, flowInput) -> bool:
        self.input = flowInput
        return True
