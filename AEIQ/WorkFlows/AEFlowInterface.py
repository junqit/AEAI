"""
AEFlowInterface - Flow 接口协议

所有 Flow 实现需遵循此协议。
  - ident:       flow 标识（属性）
  - status:      flow 执行状态（属性，AEFlowStatus）
  - delegate:     AEFlowDelegate，Flow 内部信息向外流转的出口
  - startFlow(): 启动 flow，接收 input/output 并切换到 processing
  - receiveLLMResult(): 接收输入数据
"""
from typing import Protocol, runtime_checkable, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlow import AEFlowStatus
    from .AEFlowInput import AEFlowInput
    from .AEFlowOutput import AEFlowOutput


@runtime_checkable
class AEFlowInterface(Protocol):
    """Flow 接口协议，所有 flow 需遵循此协议进行实现"""

    ident: str
    status: 'AEFlowStatus'
    delegate: 'AEFlowDelegate'

    def startFlow(self, flowInput: 'AEFlowInput', flowOutput: 'AEFlowOutput') -> None:
        """
        启动 flow：仅在 default 状态下接收 flowInput / flowOutput，并将状态切换为 processing。
        非 default 状态下调用将被忽略。

        Args:
            flowInput: flow 输入数据
            flowOutput: flow 输出数据（Map 结构）
        """
        ...

    def addFlow(self, flow: 'AEFlowInterface') -> None:
        """
        添加子 flow。

        Args:
            flow: 待添加的 flow，须符合 AEFlowInterface 协议
        """
        ...

    def receiveLLMResult(self, data: dict) -> None:
        """
        接收输入数据（map），内部解析处理。

        Flow 在执行前由外部注入输入数据 map，方法内部解析该 map，
        供后续 build_prompt / 生成等使用。

        Args:
            data: 输入数据 map
        """
        ...
