"""
AEFlowInterface - Flow 接口协议

所有 Flow 实现需遵循此协议。
  - ident:       flow 标识（属性）
  - status:      flow 执行状态（属性，AEFlowStatus）
  - inputSchema(): 输入参数数据结构（方法），flow 在不同状态下可返回不同结构
  - delegate:     AEFlowDelegate，Flow 内部信息向外流转的出口
  - receiveInputSchemaData(): 接收按 inputSchema 组织的输入数据
"""
from typing import Protocol, runtime_checkable, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlow import AEFlowStatus


@runtime_checkable
class AEFlowInterface(Protocol):
    """Flow 接口协议，所有 flow 需遵循此协议进行实现"""

    ident: str
    status: 'AEFlowStatus'
    delegate: 'AEFlowDelegate'

    def inputSchema(self) -> 'Optional[dict]':
        """
        返回当前 flow 的输入数据结构（input_schema，dict）。

        同一 flow 在不同状态下可返回不同的输入数据结构。

        Returns:
            Optional[dict]: input_schema，未设置时为 None
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
        接收输入数据（map），内部解析并按 inputSchema 校验。

        Flow 在执行前由外部注入输入数据 map，方法内部解析该 map（如按 inputSchema 校验
        required 字段），供后续 build_prompt / 生成等使用。

        Args:
            data: 输入数据 map
        """
        ...
