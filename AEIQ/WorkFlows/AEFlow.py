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
import weakref
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface
    from Context.AELLMPayload import AELLMPayload


class AEFlow(AEFlowInfo):
    """Flow 基类，继承 AEFlowInfo，实现 AEFlowInterface 与 AEFlowDelegate 协议"""

    def __init__(self, ident: Optional[str] = None):
        # ----- AEFlowInfo 属性 -----
        # ident 可由外部传入，为空则 AEFlowInfo 内部自动生成（UUID）；外部只读；
        # input_schema / out_schema / outResult 不在初始化阶段配置，后续按需设置
        super().__init__(ident=ident)
        # delegate：AEFlowDelegate，Flow 内部信息向外流转的出口
        self.delegate: "Optional[AEFlowDelegate]" = None
        # ----- 内部状态 -----
        self._flows: "Dict[str, AEFlowInterface]" = {}  # 有序 map，key 为 flow.ident
        self._current_index: int = 0                    # 当前执行的子 flow 序号

    # ==================== AEFlowInterface 实现 ====================

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def inputSchema(self) -> "AEFlowInfo":
        """
        返回当前 flow 的元信息（AEFlowInfo）。

        AEFlow 自身即 AEFlowInfo（含 ident / input_schema / out_schema）；
        子类可覆写以按状态返回不同元信息。

        Returns:
            AEFlowInfo: flow 元信息
        """
        return self

    def receiveInputSchemaData(self, data: "AEFlowInfo") -> None:
        """
        接收输入源的 AEFlowInfo，校验其 out_schema 覆盖本 flow input_schema 的 required 字段（不存储）。

        若本 flow 的 input_schema 与输入源的 out_schema 均为 JSON-Schema 形态（含 properties），
        校验本 flow required 字段是否在输入源 out_schema 的 properties 中，缺失则抛 ValueError；
        否则不做处理。子类可覆写以定制校验逻辑。

        Args:
            data: 输入源的 AEFlowInfo（其 out_schema 描述上游产出结构）

        Raises:
            ValueError: 输入源 out_schema 缺少本 flow 必填字段时
        """
        my_schema = self.input_schema
        src_schema = data.out_schema if data is not None else None
        if isinstance(my_schema, dict) and isinstance(src_schema, dict) and "properties" in src_schema:
            src_props = set(src_schema["properties"].keys())
            missing = [r for r in my_schema.get("required", []) if r not in src_props]
            if missing:
                raise ValueError(f"输入源 out_schema 缺少本 flow 必填字段: {missing}")

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

    def next_flow_input_schema(self, info: "Optional[AEFlowInfo]" = None) -> "Optional[AEFlowInfo]":
        """
        获取子 flow 的元信息（AEFlowInfo）。

        - info 非空：按 info.ident 返回该子 flow
        - info 为空：返回本层下一个（current+1）子 flow；本层无下一个时向上委托外层 delegate

        Args:
            info: 指定 flow 的元信息（用其 ident 查找）；为 None 时取下一个

        Returns:
            AEFlowInfo: 子 flow 元信息（AEFlow 即 AEFlowInfo）；无可用时返回 None
        """
        if info is not None:
            return self._flows.get(info.ident)
        order = list(self._flows.keys())
        nxt = self._current_index + 1
        if 0 <= nxt < len(order):
            return self._flows[order[nxt]]
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

    def flow_complete(self, result: "AEFlowInfo") -> None:
        """
        Flow 完成通知：result 为完成 flow 的元信息（AEFlowInfo）。

        按 result.ident 匹配 _flows：
          - 命中（本层直接子 flow 完成）→ 推进当前子 flow 序号
          - 未命中 → 向上委托 delegate.flow_complete(result)
        无返回值。

        Args:
            result: 完成 flow 的元信息（含 ident）
        """
        ident = result.ident
        if ident and ident in self._flows:
            self._current_index += 1
        elif self.delegate is not None:
            self.delegate.flow_complete(result)
