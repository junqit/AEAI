"""
AEFlowInfo - Flow 元信息基类，持有 ident / title / responsibility / input / output / status。
AEFlow 继承本类以获得这些元信息属性。

ident 可传入（默认空字符串，为空时内部生成 uuid），以便与 flowOutput.out_schema.ident 对齐；
output（AEFlowOutput，本 flow 输出结构）创建时必传，规范结构为
{"ident": <回程路由目标 ident>, "reply": <llm 占位>}：子 flow 填父 flow.ident（路由回父 flow），
根 flow 留空则内部回填为自身 ident。input（AEFlowInput）可在创建时传入（默认 None），未传时由 startFlow 设置。
"""
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from .AEFlowInput import AEFlowInput
from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from Excutor.AERuntimeExcutor import AEFunctional

# out_schema / 路由信封内 ident 字段名
AE_IDENT = "ident"

# llm_out 内默认 answer 字段名
AE_ANSWER = "reply"

# out_schema 内功能性调用唯一标识字段名（每次 flowOutput 随机生成）
AE_funcationkey = "excutor"

class AEFlowStatus(str, Enum):
    """Flow 执行状态"""
    default = "default"            # 初始状态
    processing = "processing"      # 执行中
    complete = "complete"          # 已完成


class AEFlowInfo:
    """Flow 元信息：标识、角色信息与输入/输出数据"""

    # 创建所需的数据结构说明：ident 由内部生成，无需传入
    CREATE_SCHEMA: Dict[str, Any] = {}

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        """Flow 元信息初始化。

        Args:
            flowOutput: 本 flow 输出结构（AEFlowOutput），创建时必传；其 out_schema 经
                        flowOutput(complete) 作为 llm_out 交 LLM 填充，回程按其中的 ident 路由。
            ident: flow 标识；默认空字符串，为空时内部生成 uuid。外部可显式传入以便与
                   flowOutput.out_schema.ident 对齐（如根 flow 需 complete 回程路由到自身）。
                        子 flow 应显式填父 flow.ident 以便 complete 结果路由回父 flow。
            flowInput: flow 输入数据（AEFlowInput），默认可不传（None）；传入则作为 self.input 初始值，
                        未传时仍由 startFlow 设置。命名沿用 startFlow 的 flowInput 约定。
        """
        # ident 为空时内部生成
        if not ident:
            ident = uuid.uuid4().hex
        self._ident: str = ident

        # ----- 角色信息 -----
        self.title: str = ""           # 职称
        self.responsibility: str = ""  # 职责要求

        # output：本 flow 输出结构，创建时必传（不再经 startFlow 注入）
        self.output: AEFlowOutput = flowOutput

        # input：可在初始化时传入（默认 None），未传时由 startFlow 设置
        self.input: Optional[AEFlowInput] = flowInput

        # LLM 生成的问问题模板话术：由 receiveQuestionTemplate 赋值
        self.questionTemplateResult: str = ""

        # 最终结果：complete 阶段由 flow_receive_complete 赋值，持有本 flow 的最终输出数据
        self.outResult: Optional[dict] = None

        # ----- 执行状态 -----
        self.status: AEFlowStatus = AEFlowStatus.default

    @property
    def ident(self) -> str:
        """flow 标识（只读）"""
        return self._ident

    @property
    def role_brief(self) -> str:
        """组装身份与能力范围信息，供 LLM 明确本 flow 的角色定位。

        返回形如「你的身份是：X；你的能力范围是：Y」的描述；对应字段为空时省略对应分句。
        """
        parts = []
        if len(self.title) > 0:
            parts.append(f"你的身份是：{self.title}")
        if len(self.responsibility) > 0:
            parts.append(f"你的能力范围是：{self.responsibility}")
        if len(parts) == 0:
            return ""
        return "".join(parts)

    def flowOutput(self, functional: str) -> AEFlowOutput:
        """返回本 flow 的 AEFlowOutput，schema 结构为 {ident, title, funcationkey, llm_out}。

        Args:
            functional: 功能性方法名（字符串，如 AEFunctional.flow_receive_complete），
                        直接用于注册临时处理方法；回包由 flow_receive_llm 按 AE_funcationkey
                        路由到对应方法。

        llm_out：complete 阶段必为 self.output.out_schema（本 flow 输出结构，交 LLM 填充）；
        其余阶段用默认占位 {AE_ANSWER: llm_generate("生成的答案")}。
        """
        from Context.Context.AELLMPayload import llm_generate

        # complete 阶段 llm_out 必为 self.output.out_schema；其余阶段用默认占位
        if functional == AEFunctional.flow_receive_complete and self.output is not None:
            llm_out = self.output.out_schema
        else:
            llm_out = {AE_ANSWER: llm_generate("根据职业与能力，给出最准确的答案，不可随意！！")}

        # functional 即方法名（flow_receive_*），直接注册；funcident 作为 AE_funcationkey 供回包路由
        funcationkey = self.registerFunctional(functional)

        return AEFlowOutput(out_schema={
            AE_IDENT: self.ident,
            "title": self.title,
            AE_funcationkey: funcationkey,
            AE_LLM_OUT: llm_out,
        })

    def registerFunctional(self, method: str) -> str:
        """注册临时功能性方法。funcident 为随机字符串键，method 为方法名字符串。

        Args:
            method: 方法名字符串（如 AEFunctional.flow_receive_*），executor 内部经 method_call 拼 script

        Returns:
            随机生成的 funcident，供写入 out_schema 的 AE_funcationkey 字段
        """
        funcident = uuid.uuid4().hex
        self.excutor.add_temporary(funcident, method, self)
        return funcident

    def to_map(self) -> dict:
        """返回元信息的 map 形态（ident / title / responsibility / input / output）"""
        return {
            AE_IDENT: self.ident,
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
