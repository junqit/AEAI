"""
AEAssistant - 助理生成 Flow，继承 AERole。

根据传入的 map（领域 / 用户问题等信息）驱动「专家助理」的生成，
最终输出助理定义 map（名称、领域、职责、能力、评价规则等），供后续流程加载使用。
"""
import logging

from WorkFlows.AEFlow import AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowInfo import AE_TITLE
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInterfaceImpl import AEFlowInterfaceImpl
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT
from Roles.AEBaseRole import AERole
from Roles.WorkGroup.AEWorkGroup import AEWorkGroup
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AEAssistantFunction(AEFunctional):
    """助理生成功能性方法名（继承 AEFunctional 基类）。

    每个方法接收一个 map（步骤输入 / 输出数据），由 executor 按名调用。
    """
    updateAssisstantInfo = "updateAssisstantInfo"  # 更新助理信息，传入 map
    addWorkGroups = "addWorkGroups"                # 添加工作组，传入任务内容列表


class AEAssistant(AERole):
    """助理生成 Flow：根据传入 map 生成专家助理定义。"""

    # updateAssisstantInfo 接收的 map 整体结构：llm_generate 占位说明各字段应填充内容
    updateAssisstantInfo_input = {
        AE_TITLE: llm_generate("专家职称，体现专业领域与定位"),
        "responsibility": llm_generate("专家职责要求，明确能力范围与禁止事项"),
    }

    # addWorkGroups 接收的参数格式：任务内容列表，每项为一个工作组可独立完成的任务内容
    addWorkGroups_input = [
        llm_generate("工作组可独立完成的任务内容"),
    ]

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "Assistant Generator"
        self.responsibility = (
            "根据传入的领域信息与用户问题，动态生成一个「专家」定义。\n"
            "要求：\n"
            "1. 仅生成助理的定义（名称、领域、职责、能力、评价规则等），不直接执行任务。\n"
            "2. 输出为结构化 map，供后续流程加载使用。\n"
            "3. 字段需贴合问题领域，不可随意编造。"
        )

    def updateAssisstantInfo(self, data: dict) -> bool:
        """更新助理的身份与职责（覆盖默认 title / responsibility）。

        Args:
            data: 助理配置 map，结构见 updateAssisstantInfo_input：
                  {AE_TITLE: <助理职称>, "responsibility": <助理职责要求>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        import json
        logger.info("[AEAssistant:%s] updateAssisstantInfo 收到数据:\n%s",
                    self.ident, json.dumps(data, ensure_ascii=False, indent=2, default=str) if isinstance(data, dict) else repr(data))
        if not isinstance(data, dict):
            data = {}
        self.title = data.get(AE_TITLE, "") or ""
        self.responsibility = data.get("responsibility", "") or ""

        # 收到 title/responsibility 后，发起第二步：维度目标生成
        # 用户问题以统一前缀（AE_USER_QUESTION_PREFIX）标识，作为 system 消息
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.input.content if self.input else ''}",
        })
        # 指令：列举不同维度的目标，每个目录独立可交单独工作组完成
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"根据{AE_USER_QUESTION_PREFIX}，结合自身能力与职业，给出专业的任务维度分离，每个任务可独立完成、无耦合。",
        })
        # 走 addWorkGroups：回包交 self.addWorkGroups(任务列表) 创建并启动各工作组
        flow_out = self.flowOutput(AEAssistantFunction.addWorkGroups)
        # llm_out 设为 addWorkGroups_input（任务内容列表格式），由 LLM 填充后回包作 inner 传入 addWorkGroups
        flow_out.set_llm_out(list(self.addWorkGroups_input))
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
        return True

    def addWorkGroups(self, tasks: list) -> bool:
        """根据任务内容列表添加并启动工作组子 flow。

        每个任务由一个独立工作组（AEWorkGroup）完成，互不耦合；工作组的 output.ident
        填本 assistant.ident，使其完成时路由回本 assistant 的 receive_flow_result。

        Args:
            tasks: 任务内容列表，结构见 addWorkGroups_input：
                   [<工作组可独立完成的任务内容>, ...]，每项为字符串

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        for task in tasks:
            content = task if isinstance(task, str) else str(task or "")
            wg = AEWorkGroup(
                flowOutput=AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("工作组结论")}),
            )
            AEFlowInterfaceImpl.addFlow(self, wg)
            wg.startFlow(AEFlowInput(content=content))
        return True

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(role_brief) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，含助理定义 map 占位，由 LLM 填充）

        Args:
            flowInput: flow 输入数据（content 即用户问题 / 领域描述）
        """
        if not super().startFlow(flowInput):
            return
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: self.input.content if self.input else ""})
        flow_out = self.flowOutput(AEAssistantFunction.updateAssisstantInfo)
        # flow_out 默认 llm_out 为占位，此处替换为 updateAssisstantInfo 需要的参数结构
        # （title / responsibility 占位），由 LLM 填充后回包交 updateAssisstantInfo(inner) 处理
        flow_out.set_llm_out(dict(self.updateAssisstantInfo_input))
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
