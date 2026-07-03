"""
AEFlowInfo - Flow 元信息基类，持有 ident / input_schema / out_schema / outResult。
AEFlow 继承本类以获得这些元信息属性。

创建所需数据结构见 CREATE_SCHEMA：当前仅需 ident（创建时必填，不可为空）；
input_schema / out_schema / outResult 不在创建时配置，后续按需设置。
"""
import uuid
from typing import Any, Dict, Optional


class AEFlowInfo:
    """Flow 元信息：标识、输入/输出数据结构与输出结果"""

    # 创建所需的数据结构说明：当前仅需 ident
    CREATE_SCHEMA: Dict[str, Any] = {
        "ident": {
            "type": "string",
            "required": True,
            "description": "flow 标识；创建时必填，不可为空",
        }
    }

    def __init__(self, ident: str):
        # ident 长度为 0 时内部生成
        if not ident:
            ident = uuid.uuid4().hex

        self._ident: str = ident

                # ----- 角色信息 -----
        self.title: str = ""           # 职称
        self.responsibility: str = ""  # 职责要求

        # input_schema / out_schema / outResult 不在初始化阶段配置，后续可设置
        self.input_schema: Optional[dict] = None
        self.out_schema: Optional[dict] = None
        self.outResult: Optional[Any] = None

    @property
    def ident(self) -> str:
        """flow 标识（只读）"""
        return self._ident

    @staticmethod
    def createInfo(data: Optional[dict] = None) -> dict:
        """
        返回创建信息 map（父类 AEFlowInfo 的创建方法，不依赖 cls）。

        - data 为空（None / 空 dict）→ 返回 CREATE_SCHEMA（创建数据结构说明，副本）
        - data 非空 → 将 CREATE_SCHEMA 合并进 data（data 优先）后返回

        Args:
            data: 创建信息（createInfo），可空

        Returns:
            dict: 创建信息 map
        """
        if not data:
            return dict(AEFlowInfo.CREATE_SCHEMA)
        return {**AEFlowInfo.CREATE_SCHEMA, **data}
