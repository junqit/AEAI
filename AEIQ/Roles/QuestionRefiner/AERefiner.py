"""
AERefiner - 问题精炼 Flow，继承 AEFlow。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。
"""
import logging

from WorkFlows.AEFlow import AEFlow, AEFlowStatus, AEFlowFunctional
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERole import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole, ROLE_PARAMS

logger = logging.getLogger(__name__)


class AERefinerFunctional(AEFunctional):
    """问题精炼 Flow 专属回包功能性方法名（继承 AEFunctional 的 flow_receive_* 常量，可按需扩展）。"""
    receiveRefinerQuestion = "receiveRefinerQuestion"  # 接收 LLM 精炼后的问题，传入 map
    roleChoice = "roleChoice"                            # 接收 LLM 选择的问题解决角色 type，传入 map


class AERefiner(AEFlow):
    """问题精炼 Flow：改写用户问题，输出 answer。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        # 职称 / 职责要求
        self.title = "Question Refiner"
        self.responsibility = (
            "将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。\n"
            "要求：\n"
            "1. 保持用户原始意图不变。\n"
            "2. 不增加用户未明确表达的新需求。\n"
            "3. 不进行分析、推理或回答问题。\n"
            "4. 不补充事实信息。\n"
            "5. 只优化表达方式。\n"
            "6. 输出应该直接作为后续 AI 的输入。\n"
            "如果问题已经清晰，则仅做轻微优化。"
        )
        # 问题转换后的内容（精炼后的问题）：由 receiveRefinerQuestion 从回包单独提取并存储
        self._refinedQuestion: str = ""
        # LLM 选择的问题解决角色 type（expert / workgroup / employee / reviewer）：由 roleChoice 接收并存储
        self._roleChoiceType: str = ""

    @property
    def outResult_summary(self) -> str:
        """覆写：以统一前缀（AE_USER_QUESTION_PREFIX）返回精炼后的问题。"""
        answer = self._extract_answer(self.outResult) or ""
        return f"{AE_USER_QUESTION_PREFIX}{answer}"

    @property
    def refinerQuestion(self) -> str:
        """问题转换后的内容（精炼后的问题；未接收回包时返回空串）。"""
        return self._refinedQuestion

    def receiveRefinerQuestion(self, data: dict) -> None:
        """接收精炼后问题的回包：单独提取「问题转换后的内容」并存储，再向上 complete 通知。

        回包 inner（llm_out）形如 {AE_IDENT: <chat.ident>, AE_ANSWER(reply): <问题转换后的内容>}：
        - 单独提取 reply（问题转换后的内容）存入 self._refinedQuestion，供 refinerQuestion 属性读取；
        - 交基类 flow_receive_complete 置 complete、写 outResult，并通过 delegate.flow_complete
          路由回 AEChat，驱动下一个子 flow（assistant）。

        Args:
            data: 回包内层 llm_out（含 ident / reply，reply 即问题转换后的内容）
        """
        # 单独定义「问题转换后的内容」：从回包提取精炼后的问题
        self._refinedQuestion = self._extract_answer(data) or ""
        # 拿到精炼问题后，交 LLM 选择负责解决问题的角色人选
        self.requestRoleChoice()

    def requestRoleChoice(self) -> None:
        """组装角色选择 LLM 请求：以 AEFlowRole 各角色的 type / title / responsibility 拼 system 消息，
        由 LLM 选出最适合解决本问题的角色，返回 type。

        - messages: system(角色清单 + 选择指令) / user(精炼后的问题)
        - out_schema: {type 占位}，由 LLM 填充所选角色 type
        - 走 roleChoice：回包后写入 self._roleChoiceType（不完成 flow）
        """
        # 以 AEFlowRole 各角色的 type / title / responsibility 组装可选角色清单
        role_lines = []
        for role, info in ROLE_PARAMS.items():
            role_lines.append(f"- type: {role.value}；职称：{info.title}；职责：{info.responsibility}")
        role_text = "\n".join(role_lines)
        system_content = (
            "你是一名「角色选择器」。请根据用户问题，从下列角色中选择最适合负责解决该问题的人选，"
            "仅返回所选角色的 type 字段值（expert / workgroup / employee / reviewer 之一），"
            "不要输出任何其他内容。\n"
            f"可选角色：\n{role_text}"
        )
        messages = [
            {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: system_content},
            {AE_ROLE: AEConentRole.USER.value, AE_CONTENT: f"用户问题（已精炼）：{self._refinedQuestion}"},
        ]
        flow_out = self.flowOutput(AERefinerFunctional.roleChoice)
        flow_out.set_llm_out({"type": llm_generate("所选角色的 type，取值之一：expert / workgroup / employee / reviewer")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def roleChoice(self, data) -> None:
        """接收 LLM 选择的问题解决角色 type，存入 self._roleChoiceType（不完成 flow）。

        Args:
            data: 回包内层 llm_out，形如 {"type": <expert / workgroup / employee / reviewer>}；
                  若直接为字符串则视为 type 值
        """
        if isinstance(data, dict):
            self._roleChoiceType = data.get("type") or ""
        elif isinstance(data, str):
            self._roleChoiceType = data.strip()
        else:
            self._roleChoiceType = ""

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(title) / system(responsibility) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，含 reply 占位，由 LLM 生成精炼后的问题）

        Args:
            flowInput: flow 输入数据（content 即用户原始问题）
        """
        if not super().startFlow(flowInput):
            return


        self.requestQuestionTemplate()
        # messages = []
        # role_brief = self.role_brief
        # if len(role_brief) > 0:
        #     messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: self.input.content if self.input else ""})
        # # 用本 flow 的 output.out_schema 作 llm_out，由 flowOutput 打包成路由信封
        # # （ident/title/funcationkey + llm_out）；receiveRefinerQuestion 随机 funcident，回包据此路由
        # flow_out = self.flowOutput(AERefinerFunctional.receiveRefinerQuestion)
        # # 切到独立 receiveRefinerQuestion 后，flowOutput 走非 complete 分支会丢失 output.out_schema
        # # （含回程路由所需的 ident）；用本 flow 的 output.out_schema 补回 llm_out，保持 complete 风格输出结构
        # flow_out.set_llm_out(self.output.out_schema)
        # payload = AELLMPayload(
        #     messages=messages,
        #     out_schema=flow_out.out_schema,
        # )
        # # 发送前置状态为 complete，注入 out_schema 后回包按 complete 处理
        # self.send_llm_payload(payload)
