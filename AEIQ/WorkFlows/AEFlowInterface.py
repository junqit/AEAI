"""
AEFlowInterface - Flow 接口协议

所有 Flow 实现需遵循此协议。
  - ident:       flow 标识（属性）
  - inputSchema(): 输入参数数据结构（方法），flow 在不同状态下可返回不同结构
  - delegate:     AEFlowDelegate，Flow 内部信息向外流转的出口
  - receiveInputSchemaData(): 接收按 inputSchema 组织的输入数据
"""
from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInfo import AEFlowInfo


@runtime_checkable
class AEFlowInterface(Protocol):
    """Flow 接口协议，所有 flow 需遵循此协议进行实现"""

    ident: str
    delegate: 'AEFlowDelegate'

    def inputSchema(self) -> 'AEFlowInfo':
        """
        返回当前 flow 的元信息（AEFlowInfo，含 ident / input_schema / out_schema）。

        同一 flow 在不同状态下可返回不同的元信息。

        Returns:
            AEFlowInfo: flow 元信息
        """
        ...

    def addFlow(self, flow: 'AEFlowInterface') -> None:
        """
        添加子 flow。

        Args:
            flow: 待添加的 flow，须符合 AEFlowInterface 协议
        """
        ...

    def receiveInputSchemaData(self, data: 'AEFlowInfo') -> None:
        """
        接收输入源的元信息（AEFlowInfo）。

        Flow 在执行前由外部注入输入源的 AEFlowInfo（其 out_schema 描述上游产出结构），
        供校验 / build_prompt / 生成等使用。

        Args:
            data: 输入源的 AEFlowInfo
        """
        ...
