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


@runtime_checkable
class AEFlowInterface(Protocol):
    """Flow 接口协议，所有 flow 需遵循此协议进行实现"""

    ident: str
    delegate: 'AEFlowDelegate'

    def inputSchema(self) -> dict:
        """
        返回当前状态下的输入参数数据结构（JSON Schema 或结构描述）。

        同一 flow 在不同状态下可返回不同的数据结构。

        Returns:
            dict: 输入参数数据结构
        """
        ...

    def addFlow(self, flow: 'AEFlowInterface') -> None:
        """
        添加子 flow。

        Args:
            flow: 待添加的 flow，须符合 AEFlowInterface 协议
        """
        ...

    def receiveInputSchemaData(self, data: dict) -> None:
        """
        接收按 inputSchema 组织的输入数据。

        Flow 在执行前由外部注入其输入数据，供后续 build_prompt / 生成等使用。

        Args:
            data: 输入数据，结构应与 inputSchema() 返回的 schema 对应
        """
        ...
