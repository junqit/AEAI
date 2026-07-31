"""
AEFlowInfo - Flow 元信息基类，持有 ident / input / output / status。
AEFlow 继承本类以获得这些元信息属性。

本类只管工作流元信息与流转所需的结构（generateFlowOutput）；registerFunctional 依赖
self.excutor（由 AEFlow 持有），故置于 WorkFlows.AEFlow。角色相关信息（title / responsibility /
roleGoal / rolePrompt 及 role_brief / outResult_summary / 汇总等）属 Roles.AERoleBase，
不在本类声明或读取。

ident 可传入（默认空字符串，为空时内部生成 uuid），以便与 flowOutput.out_schema.ident 对齐；
output（AEFlowOutput，本 flow 输出结构）创建时必传，规范结构为
{"ident": <回程路由目标 ident>, "reply": <llm 占位>}：子 flow 填父 flow.ident（路由回父 flow），
根 flow 留空则内部回填为自身 ident。input（AEFlowInput）可在创建时传入（默认 None），未传时由 startFlow 设置。
"""
import uuid
from enum import Enum
from typing import Optional

from .AEFlowInput import AEFlowInput
from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from Tools.Excutor.AERuntimeExcutor import AEFunctional


# out_schema / 路由信封内 ident 字段名
AE_IDENT = "ident"

# out_schema / 路由信封内 title 字段名（字段常量保留，供 Context 等使用；WorkFlows 信封不再写入）
AE_TITLE = "title"

# llm_out 内默认 answer 字段名
AE_ANSWER = "reply"

# llm_out 内「需要提问者确认的信息」字段名
AE_CONFIRM = "confirm"

# out_schema 内功能性调用唯一标识字段名（每次 generateFlowOutput 随机生成）
AE_funcationkey = "excutor"

class AEFlowStatus(str, Enum):
    """Flow 执行状态"""
    default = "default"            # 初始状态
    processing = "processing"      # 执行中
    complete = "complete"          # 已完成


class AEFlowInfo:
    """Flow 元信息：标识、输入/输出数据与执行状态。角色相关信息见 Roles.AERoleBase。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        """Flow 元信息初始化。

        Args:
            flowOutput: 本 flow 输出结构（AEFlowOutput），创建时必传；其 out_schema 经
                        generateFlowOutput(complete) 作为 llm_out 交 LLM 填充，回程按其中的 ident 路由。
            ident: flow 标识；默认空字符串，为空时内部生成短 ident。外部可显式传入以便与
                   flowOutput.out_schema.ident 对齐（如根 flow 需 complete 回程路由到自身）。
                        子 flow 应显式填父 flow.ident 以便 complete 结果路由回父 flow。
            flowInput: flow 输入数据（AEFlowInput），默认可不传（None）；传入则作为 self.input 初始值，
                        未传时仍由 startFlow 设置。命名沿用 startFlow 的 flowInput 约定。
        """
        if not ident:
            ident = uuid.uuid4().hex
        super().__init__()
        self._ident: str = ident

        self.output: AEFlowOutput = flowOutput

        self.input: Optional[AEFlowInput] = flowInput

        self.outResult: Optional[dict] = None

        self.status: AEFlowStatus = AEFlowStatus.default

        self.deepth: int = 1

    @property
    def ident(self) -> str:
        """flow 标识（只读）"""
        return self._ident

    def generateFlowOutput(self, functional: str) -> AEFlowOutput:
        """返回本 flow 的 AEFlowOutput，schema 结构为 {ident, funcationkey, llm_out}。

        Args:
            functional: 功能性方法名（字符串，如 AEFunctional.flow_receive_complete），
                        直接用于注册临时处理方法；回包由 flow_receive_llm 按 AE_funcationkey
                        路由到对应方法。

        llm_out：complete 阶段必为 self.output.out_schema（本 flow 输出结构，交 LLM 填充）；
        其余阶段用默认占位 {AE_ANSWER: llm_generate("生成的答案")}。
        """
        from Context.Context.AELLMPayload import llm_generate

        if functional == AEFunctional.flow_receive_complete and self.output is not None:
            llm_out = self.output.out_schema
        else:
            llm_out = {AE_ANSWER: llm_generate("给出最准确的答案，不可随意！！")}

        funcationkey = self.registerFunctional(functional)

        return AEFlowOutput(out_schema={
            AE_IDENT: self.ident,
            AE_funcationkey: funcationkey,
            AE_LLM_OUT: llm_out,
        })
