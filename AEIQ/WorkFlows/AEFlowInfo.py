"""
AEFlowInfo - Flow 元信息基类，持有 ident / input_schema / out_schema / outResult。
AEFlow 继承本类以获得这些元信息属性。

- ident：可由外部传入，为空则内部自动生成（UUID）；外部只读
- input_schema / out_schema / outResult：可设置，不在初始化阶段配置
"""
import uuid
from typing import Any, Optional


class AEFlowInfo:
    """Flow 元信息：标识、输入/输出数据结构与输出结果"""

    def __init__(self, ident: Optional[str] = None):
        # ident 可由外部传入；为空（None / 空串）则内部自动生成（UUID）
        self._ident: str = ident if ident else uuid.uuid4().hex
        # input_schema / out_schema / outResult 不在初始化阶段配置，后续可设置
        self.input_schema: Optional[dict] = None
        self.out_schema: Optional[dict] = None
        self.outResult: Optional[Any] = None

    @property
    def ident(self) -> str:
        """flow 标识（只读）"""
        return self._ident
