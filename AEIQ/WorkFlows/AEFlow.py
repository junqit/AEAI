"""
AEFlow - Flow 基类，同时实现 AEFlowInterface 与 AEFlowDelegate 协议。

作为 AEFlowInterface：ident / inputSchema() / delegate / addFlow。
作为 AEFlowDelegate：get_flow_input_schema / flow_llm / flow_complete，
  供子 flow 通过本类向外流转信息。
"""
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface
    from Context.AELLMPayload import AELLMPayload


class AEFlow:
    """Flow 基类，实现 AEFlowInterface 与 AEFlowDelegate 协议"""

    def __init__(self, ident: str = ""):
        self.ident: str = ident
        # AEFlowDelegate：Flow 内部信息向外流转的出口（普通属性，满足 AEFlowInterface 协议）
        self.delegate: "Optional[AEFlowDelegate]" = None
        # 有序 map：key 为 flow.ident，value 为子 flow
        self._flows: "Dict[str, AEFlowInterface]" = {}
        # 当前执行的子 flow 序号，用于 get_flow_input_schema 的"下一个"语义
        self._current_index: int = 0

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate"""
        self.delegate = delegate

    def addFlow(self, flow: "AEFlowInterface") -> None:
        """
        添加子 flow（实现 AEFlowInterface）。

        添加前把 flow.delegate 设置为当前 flow 的 delegate；
        以 flow.ident 为 key 存入有序 map。

        Args:
            flow: 待添加的 flow，须符合 AEFlowInterface 协议
        """
        flow.set_delegate(self)
        self._flows[flow.ident] = flow

    # ==================== AEFlowDelegate 实现 ====================

    def get_flow_input_schema(self, ident: Optional[str] = None) -> Optional[dict]:
        """
        获取输入数据结构（实现 AEFlowDelegate）。

        Args:
            ident: 指定子 flow 的 ident；为 None 时返回下一个（当前 +1）子 flow 的 inputSchema

        Returns:
            dict: 输入参数数据结构；无可用时返回 None
        """
        if ident:
            flow = self._flows.get(ident)
            return flow.inputSchema() if flow is not None else None
        order = list(self._flows.keys())
        nxt = self._current_index + 1
        if 0 <= nxt < len(order):
            return self._flows[order[nxt]].inputSchema()
        return None

    async def flow_llm(self, payload: "AELLMPayload") -> str:
        """
        发送 AELLMPayload 调用 LLM（实现 AEFlowDelegate）。
        向上转发给当前 flow 的 delegate。

        Args:
            payload: AELLMPayload 结构体

        Returns:
            str: LLM 回复文本
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        return await self.delegate.flow_llm(payload)

    def flow_complete(self, result: dict) -> dict:
        """
        Flow 完成，按下一个 flow 的 inputSchema 结构整理 result 并返回（实现 AEFlowDelegate）。
        完成后推进当前子 flow 序号。

        Args:
            result: Flow 产出的数据

        Returns:
            dict: 按下游 input_schema 整理后的 map
        """
        schema = self.get_flow_input_schema(None)
        if isinstance(result, dict) and isinstance(schema, dict) and "properties" in schema:
            allowed = set(schema["properties"].keys())
            result = {k: v for k, v in result.items() if k in allowed}
        self._current_index += 1
        return result

    # ==================== AEFlowInterface 实现 ====================

    def inputSchema(self) -> dict:
        """
        返回当前状态下的输入参数数据结构（实现 AEFlowInterface）。

        子类按自身状态覆写，可返回不同的数据结构。

        Returns:
            dict: 输入参数数据结构
        """
        raise NotImplementedError("子类必须实现 inputSchema()")
