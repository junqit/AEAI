"""
AEFlowInfo - Flow 元信息基类，持有 ident / title / responsibility / input / output / status。
AEFlow 继承本类以获得这些元信息属性。

创建所需数据结构见 CREATE_SCHEMA：当前仅需 ident（创建时必填，不可为空）；
input / output 不在创建时配置，后续按需设置。
"""
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from .AEFlowInput import AEFlowInput
from .AEFlowOutput import AEFlowOutput

# llm_out 内默认 answer 字段名
AE_ANSWER = "answer"

# out_schema 内功能性调用唯一标识字段名（每次 flowOutput 随机生成）
AE_funcationkey = "funcationkey"


class AEFlowStatus(str, Enum):
    """Flow 执行状态"""
    default = "default"            # 初始状态
    processing = "processing"      # 执行中
    complete = "complete"          # 已完成


class AEFlowInfo:
    """Flow 元信息：标识、角色信息与输入/输出数据"""

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

        # input / output 不在初始化阶段配置，后续可设置
        self.input: Optional[AEFlowInput] = None
        self.output: Optional[AEFlowOutput] = None

        # ----- 执行状态 -----
        self.status: AEFlowStatus = AEFlowStatus.default

    @property
    def ident(self) -> str:
        """flow 标识（只读）"""
        return self._ident

    def flowOutput(self, functional: str) -> AEFlowOutput:
        """返回本 flow 的 AEFlowOutput，schema 结构为 {ident, title, funcationkey, llm_out}。

        Args:
            functional: AEFlowFunctional 方法名（flow_receive_default/processing/complete），
                        直接用于注册临时处理方法；回包由 flow_receive_llm 按 AE_funcationkey
                        路由到对应方法。

        llm_out 复用本 flow 的 output.out_schema；output 未设置时用默认占位
        {AE_ANSWER: llm_generate("生成的答案")}（llm_generate 必含）。
        """
        from Context.Context.AELLMPayload import llm_generate

        if self.output is not None:
            llm_out = self.output.out_schema
        else:
            llm_out = {AE_ANSWER: llm_generate("生成的答案")}

        # functional 即方法名（flow_receive_*），直接注册；funcident 作为 AE_funcationkey 供回包路由
        funcationkey = self.registerFunctional(functional)

        return AEFlowOutput(out_schema={
            "ident": self.ident,
            "title": self.title,
            AE_funcationkey: funcationkey,
            "llm_out": llm_out,
        })

    def registerFunctional(self, method: str) -> str:
        """注册临时功能性方法，funcident 用随机创建的唯一标识。

        funcident 随机生成（uuid hex），与 out_schema 的 AE_funcationkey 对应，
        回包据此路由到 method 指定的 flow_receive_* 方法；temporary 执行后自动清除。

        Args:
            method: 方法名（flow_receive_*），经 excutor.method_call 拼成 self.<method>(inner)

        Returns:
            随机生成的 funcident，供写入 out_schema 的 AE_funcationkey 字段
        """
        funcident = uuid.uuid4().hex
        self.excutor.add_temporary(funcident, method, self)
        return funcident

    def to_map(self) -> dict:
        """返回元信息的 map 形态（ident / title / responsibility / input / output）"""
        return {
            "ident": self.ident,
            "title": self.title,
            "responsibility": self.responsibility,
            "input": self.input,
            "output": self.output,
        }

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
