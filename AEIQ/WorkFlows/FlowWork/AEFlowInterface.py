"""
AEFlowInterface - Flow 接口协议 + AEFlowInterfaceImpl 实例实现（mixin），同文件组织。

- AEFlowInterface（Protocol）：声明所有 Flow 需遵循的接口（ident / status / delegate / receive_llm_response）。
- AEFlowInterfaceImpl（mixin）：提供 receive_llm_response / flow_receive_llm / send_llm_request
  的实例实现，由 AEFlow 继承获得。receive_flow_input / add_flow 在 AEFlowDelegateImpl。
"""
import logging
from typing import Protocol, runtime_checkable, TYPE_CHECKING, Optional

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInput import AEFlowInput, AEFlowStatus
from .AEFlowInfo import AE_IDENT, AE_CONTENT, AE_funcationkey
from .AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowOutput import AEFlowOutput

logger = logging.getLogger(__name__)


@runtime_checkable
class AEFlowInterface(Protocol):
    """Flow 接口协议，所有 flow 需遵循此协议进行实现"""

    ident: str
    status: 'AEFlowStatus'
    delegate: 'AEFlowDelegate'

    def receive_llm_response(self, data: dict) -> None:
        """
        接收输入数据（map），内部解析处理。

        Args:
            data: 输入数据 map
        """
        ...


class AEFlowInterfaceImpl:
    """AEFlowInterfaceImpl 协议方法实现（mixin），由 AEFlow 继承获得这些方法。

    提供 receive_llm_response / flow_receive_llm / send_llm_request 的实例实现。
    receive_flow_input / add_flow 已迁入 AEFlowDelegateImpl。
    """

    def receive_llm_response(self, data: dict) -> None:
        """
        接收输入数据（map），按其中的 ident 路由；所有分支均需闭环（不得静默 return 致 flow 卡死）：

          - data 非 map → 以错误完成本 flow 闭环（flow_receive_complete + error 事件）
          - ident == self.ident → 本层处理，交 flow_receive_llm（其内部对异常数据亦闭环）
          - ident 命中 _flows 内子 flow → 转发内层 out_schema 给该子 flow（receive_llm_response）
          - ident 既非自身、也未命中子 flow → 以错误完成本 flow 闭环（flow_receive_complete + error 事件）

        data 约定为 flow_send_llm_request 向上转发时的封装形态：{"ident": <目标 ident>, "llm_out": <...>}，
        每层路由消费一层 ident，逐层下传内层 out_schema；最内层叶子无 ident，由该层 flow 自己处理。
        """
        if not isinstance(data, dict):
            logger.error(
                "[d=%s] 收到的数据非 map，无法解析，以错误完成本 flow 闭环: %r",
                self.deepth, data,
            )
            self.flow_receive_complete({AE_IDENT: self.ident, AE_CONTENT: "LLM 回包非 map，无法解析"}, AEFlowCompletEvent.error)
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

    def flow_receive_llm(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 receive_llm_response 路由到自身、已解析出的 out_schema 数据。

        按 out_schema 内的 AE_funcationkey 字段从 self.excutor 取对应脚本并执行；
        该 key 由发送方 generateFlowOutput 注册时随机生成，对应一个 flow_receive_* 方法。

        out_schema 内无 AE_funcationkey 字段、或其值未在 excutor 内注册时，以错误完成本 flow 闭环。
        子类可经 excutor.add_default / add_temporary 自定义处理，或覆写各 flow_receive_* 方法；
        temporary 注册执行后由 excutor 自动清除。

        Args:
            out_schema: 从输入 map 中解析出的 out_schema 数据（含 AE_funcationkey / llm_out 字段）
        """
        if not isinstance(out_schema, dict):
            logger.error(
                "[d=%s] out_schema 非 map，以错误完成本 flow 避免卡死: %r",
                self.deepth, out_schema,
            )
            self.flow_receive_complete({AE_IDENT: self.ident, AE_CONTENT: "LLM 回包非 map，无法处理"}, AEFlowCompletEvent.error)
            return
        command = out_schema.get(AE_funcationkey)
        inner = out_schema.get(AE_LLM_OUT)
        if not self.excutor.contains(command):
            logger.error(
                "[d=%s] out_schema 内 funcationkey=%r 无效或缺失，以错误完成本 flow 避免卡死: %r",
                self.deepth, command, out_schema,
            )
            self.flow_receive_complete({AE_IDENT: self.ident, AE_CONTENT: "LLM 回包 funcationkey 无效，无法路由处理"}, AEFlowCompletEvent.error)
            return
        self.excutor.exec(command, inner)
