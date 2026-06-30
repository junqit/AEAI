"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议

Flow 在执行过程中通过该 Delegate 与外部（如 WorkFlow 运行器 / ContextManager）交互：
  1. get_flow_input_schema  获取输入数据结构
  2. flow_llm               发送 AELLMPayload 调用 LLM
  3. flow_complete          Flow 完成，按 input_schema 结构返回 map

任何类只要实现以下方法即视为符合协议，无需继承。
"""
from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from Context.AELLMPayload import AELLMPayload


@runtime_checkable
class AEFlowDelegate(Protocol):
    """Flow 委托协议：Flow 内部信息向外流转的出口"""

    def get_flow_input_schema(self, ident: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取输入数据结构。

        Args:
            ident: 指定流的标识；为 None / 空时返回下个工作流的输入参数结构

        Returns:
            输入数据结构（JSON Schema 或结构描述）；无可用时返回 None
        """
        ...

    async def flow_llm(self, payload: 'AELLMPayload') -> str:
        """
        发送 AELLMPayload 结构体调用 LLM。

        Args:
            payload: AELLMPayload 结构体

        Returns:
            str: LLM 回复文本
        """
        ...

    def flow_complete(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flow 完成，根据获取到的 input_schema 结构返回 map 结构。

        Args:
            result: Flow 产出的数据

        Returns:
            按 input_schema 结构组织后的 map
        """
        ...
