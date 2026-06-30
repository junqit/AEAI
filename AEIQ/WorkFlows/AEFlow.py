"""
AEFlow - Flow 基类，同时实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

AEFlowInterface 实现（flow 自身接口）：
  - ident / delegate（属性）
  - inputSchema()              返回输入参数数据结构
  - receiveInputSchemaData()   接收按 inputSchema 组织的输入数据
  - addFlow()                  添加子 flow

AEFlowDelegate 实现（子 flow 通过本类向外流转）：
  - next_flow_input_schema()   获取（下一个）子 flow 的输入数据结构
  - flow_llm()                 发送 AELLMPayload 调用 LLM
  - flow_complete()            Flow 完成，按下游 inputSchema 整理结果
"""
import uuid
import weakref
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface
    from Context.AELLMPayload import AELLMPayload


class AEFlow:
    """Flow 基类，实现 AEFlowInterface 与 AEFlowDelegate 协议"""

    def __init__(self):
        # ----- AEFlowInterface 属性 -----
        # ident 由 flow 自身生成（UUID），不由外部传入
        self.ident: str = uuid.uuid4().hex
        # delegate：AEFlowDelegate，Flow 内部信息向外流转的出口
        self.delegate: "Optional[AEFlowDelegate]" = None
        # ----- 内部状态 -----
        self._flows: "Dict[str, AEFlowInterface]" = {}  # 有序 map，key 为 flow.ident
        self._current_index: int = 0                    # 当前执行的子 flow 序号

    # ==================== AEFlowInterface 实现 ====================

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def inputSchema(self) -> dict:
        """
        返回当前状态下的输入参数数据结构。

        子类按自身状态覆写，可返回不同的数据结构。

        Returns:
            dict: 输入参数数据结构
        """
        raise NotImplementedError("子类必须实现 inputSchema()")

    def receiveInputSchemaData(self, data: dict) -> None:
        """
        接收输入数据并按 inputSchema() 校验（不存储）。

        若 inputSchema() 返回 JSON-Schema 形态（含 properties），校验 required 字段，
        缺失则抛 ValueError；否则不做处理。子类可覆写以定制校验逻辑。

        Args:
            data: 输入数据，结构应与 inputSchema() 返回的 schema 对应

        Raises:
            ValueError: 缺少 required 字段时
        """
        schema = self.inputSchema()
        if isinstance(schema, dict) and isinstance(data, dict) and "properties" in schema:
            missing = [r for r in schema.get("required", []) if r not in data]
            if missing:
                raise ValueError(f"输入数据缺少必填字段: {missing}")

    def addFlow(self, flow: "AEFlowInterface") -> None:
        """
        添加子 flow。

        添加前把 flow.delegate 设置为当前 flow（弱引用）；
        以 flow.ident 为 key 存入有序 map。

        Args:
            flow: 待添加的 flow，须符合 AEFlowInterface 协议
        """
        flow.set_delegate(self)
        self._flows[flow.ident] = flow

    # ==================== AEFlowDelegate 实现 ====================

    def next_flow_input_schema(self, ident: Optional[str] = None) -> Optional[dict]:
        """
        获取输入数据结构。

        - ident 非空：返回该子 flow 的 inputSchema
        - ident 为空：返回本层下一个（current+1）子 flow 的 inputSchema；
          本层无下一个时，向上委托外层 delegate 继续查找

        Args:
            ident: 指定子 flow 的 ident；为 None 时取下一个

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
        # 本层无下一个子 flow：向上委托外层 delegate
        if self.delegate is not None:
            return self.delegate.next_flow_input_schema()
        return None

    async def flow_llm(self, payload: "AELLMPayload") -> str:
        """
        发送 AELLMPayload 调用 LLM。

        AEFlow 自身不持有 LLM 客户端，真实发送由外层 delegate（具体 AEFlowDelegate 实现，
        如 AEContextManager 适配器）完成；本方法校验 delegate 后向上转发。

        Args:
            payload: AELLMPayload 结构体

        Returns:
            str: LLM 回复文本

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        return await self.delegate.flow_llm(payload)

    def flow_complete(self, result: dict) -> dict:
        """
        子 flow 完成：从 result 取 ident 匹配 _flows 内的工作流，
        命中则把 result 传给该 flow 的 receiveInputSchemaData（按其 inputSchema 校验）；并推进序号。

        Args:
            result: 当前子 flow 产出的数据，需含 ident 指向下一个工作流

        Returns:
            dict: 原始 result
        """
        ident = result.get("ident") if isinstance(result, dict) else None
        if ident:
            target = self._flows.get(ident)
            if target is not None:
                target.receiveInputSchemaData(result)
        self._current_index += 1
        return result
