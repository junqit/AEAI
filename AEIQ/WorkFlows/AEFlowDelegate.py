"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议

Flow 在执行过程中通过该 Delegate 与外部（如 WorkFlow 运行器 / ContextManager）交互：
  1. flow_llm_request                发送 AELLMPayload 调用 LLM
  2. flow_complete           Flow 完成，按 input_schema 结构返回 map
  3. flow_add_next_flow      添加下一个待执行的子 flow

任何类只要实现以下方法即视为符合协议，无需继承。
"""
from enum import Enum
from typing import Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from Context.Context.AELLMPayload import AELLMPayload
    from .AEFlowInterface import AEFlowInterface


class AEFlowCompletEvent(str, Enum):
    """Flow 完成事件（delegate.flow_complete 传入）：区分完成后的后续动作"""
    default = "default"            # 完成回到默认（普通完成）
    startFlow = "startFlow"        # 完成并启动下一个 flow


@runtime_checkable
class AEFlowDelegate(Protocol):
    """Flow 委托协议：Flow 内部信息向外流转的出口"""

    def flow_llm_request(self, payload: 'AELLMPayload') -> None:
        """
        发送 AELLMPayload 结构体调用 LLM（无返回值）。

        Args:
            payload: AELLMPayload 结构体
        """
        ...

    def flow_complete(self, result: dict, event: 'AEFlowCompletEvent') -> None:
        """
        Flow 完成通知：result 为完成 flow 的元信息（map），event 为完成事件。

        Args:
            result: 完成 flow 的元信息 map（含 ident）
            event: 完成事件（AEFlowCompletEvent.default / startFlow）
        """
        ...

    def flow_add_next_flow(self, flow: 'AEFlowInterface') -> None:
        """
        添加下一个待执行的子 flow。

        Args:
            flow: 待添加的子 flow，须符合 AEFlowInterface 协议
        """
        ...
