"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议

Flow 在执行过程中通过该 Delegate 与外部（如 WorkFlow 运行器 / ContextManager）交互：
  1. next_flow_input_schema  获取输入数据结构
  2. flow_llm                发送 AELLMPayload 调用 LLM
  3. flow_complete           Flow 完成，按 input_schema 结构返回 map

任何类只要实现以下方法即视为符合协议，无需继承。
"""
from typing import Optional, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from Context.AELLMPayload import AELLMPayload
    from .AEFlowInfo import AEFlowInfo
    from .AEFlow import AEFlowStatus


@runtime_checkable
class AEFlowDelegate(Protocol):
    """Flow 委托协议：Flow 内部信息向外流转的出口"""

    def next_flow_input_schema(self, info: Optional['AEFlowInfo'] = None) -> Optional['AEFlowInfo']:
        """
        获取子 flow 的元信息。

        Args:
            info: 指定 flow 的元信息（用其 ident 查找）；为 None / 空时返回下个工作流的元信息

        Returns:
            AEFlowInfo：flow 元信息（含 ident / input_schema / out_schema）；无可用时返回 None
        """
        ...

    def flow_llm(self, payload: 'AELLMPayload') -> None:
        """
        发送 AELLMPayload 结构体调用 LLM（无返回值）。

        Args:
            payload: AELLMPayload 结构体
        """
        ...

    def flow_complete(self, result: dict, flowStatus: 'AEFlowStatus') -> None:
        """
        Flow 完成通知：result 为完成 flow 的元信息（map），flowStatus 为其状态。

        Args:
            result: 完成 flow 的元信息 map（含 ident）
            flowStatus: 完成 flow 的状态
        """
        ...
