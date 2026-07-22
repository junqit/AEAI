"""
AEEmployee - 员工 Flow，继承 AERole。

完成单一流水线的工作：承接上游分配的一条流水线，调用 LLM / Tools 执行其各环节，
产出可被上游整合的结构化结果。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_TITLE, AE_ANSWER, AE_CONFIRM
from Context.Context.AELLMPayload import AELLMPayload, AEEnvParamType, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Tools.Scrips import AEScript
from Roles.AERole import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole, get_role_param
from Roles.AEBaseRole import AERole

logger = logging.getLogger(__name__)


class AEEmployeeFunction(AEFunctional):
    """员工 Flow 专属回包功能性方法名（继承 AEFunctional 的 flow_receive_* 常量，可按需扩展）。"""
    receiveQuestionType = "receiveQuestionType"  # 接收 LLM 判定的问题处理类型（script / other），传入 map
    receiveScripts = "receiveScripts"  # 接收 LLM 返回的多个 AEScript 任务，传入 map


class AEEmployee(AERole):
    """员工 Flow：完成单一流水线的工作。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "Employee"
        self.responsibility = (
            "完成单一流水线的工作。\n"
            "要求：\n"
            "1. 仅负责本流水线的执行，不跨流水线、不跨维度规划与决策。\n"
            "2. 调用模型或工具完成流水线各环节（检索 / 分析 / 生成 / 转换等）。\n"
            "3. 产出可直接被上游整合的结构化结果。\n"
            "4. 遇到不明确处向上回传，由工作组或专家裁决。"
        )
        # 问题处理类型判定结果（script / other）：由 receiveQuestionType 赋值
        self._questionType: str = ""

    def roleDescription(self) -> str:
        """角色描述：返回本角色（员工）的职称与职责。"""
        info = get_role_param(AEFlowRole.employee)
        return f"{info.title}：{info.responsibility}"

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，先 requestRoleInformation 生成自身 title/能力，回包 receiveRoleInfomation 后再执行实际任务。

        Args:
            flowInput: flow 输入数据（content 即工作组下发的子任务）
        """
        if not super().startFlow(flowInput):
            logger.warning("[AEEmployee:%s] startFlow 失败：基类未启动（非 default 状态），忽略", self.ident)
            return
        # 先请求 LLM 生成自身工作名称与能力范围（回包走 receiveRoleInfomation，再发送实际任务）
        self.requestRoleInformation()

    def receiveRoleInfomation(self, data: dict) -> bool:
        """接收角色信息（title/responsibility/rolePrompt）后，请求生成问题优化提示（requestOptimizeInput）。"""
        result = super().receiveRoleInfomation(data)
        # 角色信息生成后，交 LLM 生成问题优化提示（回包走 receiveOptimizeInput）
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题（AE_ANSWER）：存入 optimizePromptResult，再请求判定是否需要脚本处理。

        - AE_ANSWER 非空：优化后的问题，存入 self.optimizePromptResult，并调用 requestQuestionType 判定处理方式。
        - AE_CONFIRM 非空：需提问者确认的信息（此时 AE_ANSWER 为空），仅记录。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <优化后的问题>, AE_CONFIRM: <需确认信息>}（二选一）

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        confirm = data.get(AE_CONFIRM) if isinstance(data, dict) else None
        confirm = (confirm or "").strip() if isinstance(confirm, str) else ""
        if confirm:
            logger.info("[AEEmployee:%s] 收到需确认信息:\n%s", self.ident, confirm)
            return True
        self.optimizePromptResult = result or ""
        logger.info("[AEEmployee:%s] 收到优化后的问题:\n%s", self.ident, self.optimizePromptResult)
        # 先判定是否需要脚本程序处理，再据结果分流（receiveQuestionType）
        self.requestQuestionType()
        return True

    def requestQuestionType(self) -> None:
        """请求 LLM 判定当前优化后的问题是否需要脚本程序处理。

        - messages: system(role_brief) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(判定指令)
        - out_schema: {result 占位}，由 LLM 填充 "script" 或 "other"
        - 走 receiveQuestionType：回包后据 result 决定走脚本流程或其它处理
        """
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 用户问题以统一前缀标明，作为 system 消息
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.optimizePromptResult}",
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请判定{AE_USER_QUESTION_PREFIX}是否需要通过编写并执行脚本程序"
                "（python / shell / ruby）来处理，并将判定结果填入 result 字段："
                "script（需要脚本）或 other（不需要脚本，走其它方式）。"
            ),
        })
        flow_out = self.flowOutput(AEEmployeeFunction.receiveQuestionType)
        flow_out.set_llm_out({"result": llm_generate("script 或 other")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveQuestionType(self, data: dict) -> bool:
        """接收 LLM 判定结果（result: script / other），据结果分流。

        - script：走 requestScripts 生成并执行脚本。
        - other：无需脚本，以优化后的问题作为本员工结论完成 flow。

        Args:
            data: 回包内层 llm_out，形如 {"result": <script / other>}；若直接为字符串则视为 result 值

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = data.get("result") if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        result = (result or "").strip().lower()
        self._questionType = result
        logger.info("[AEEmployee:%s] 问题类型判定: result=%s", self.ident, result)
        if result == "script":
            # 需要脚本：以优化后的问题请求生成并执行脚本
            self.requestScripts(self.optimizePromptResult)
            return True
        # other：无需脚本，直接请求 LLM 对优化后的问题给出结论
        self.requestDirectAnswer()
        return True

    def requestDirectAnswer(self) -> None:
        """无需脚本时，直接请求 LLM 对优化后的问题给出结论。

        - messages: system(role_brief) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(直接作答指令)
        - out_schema: 走 flow_receive_complete，回包直接完成本员工（outResult 取 self.output.out_schema，含 AE_ANSWER）
        """
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 用户问题以统一前缀标明，作为 system 消息
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.optimizePromptResult}",
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"请直接回答{AE_USER_QUESTION_PREFIX}，给出准确、完整的结论。",
        })
        # 走 flow_receive_complete：回包直接完成本员工
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def requestScripts(self, question: str) -> None:
        """以传入的问题（当前 AE_ANSWER）请求 LLM 生成多个 AEScript 任务。

        - messages: system(role_brief) / user(问题 + 生成脚本任务指令)
        - out_schema: {AE_ANSWER: 脚本任务 JSON 数组 占位}，由 LLM 填充
        - 走 receiveScripts：回包后由 receiveScripts 解析为 AEScript 列表并加入 self._flows

        Args:
            question: 当前 AE_ANSWER（精炼后的问题）
        """
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 问题以统一前缀标明，作为 system 消息
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}",
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请针对上述问题生成多个可独立执行的脚本任务，严格输出 JSON 数组，每项结构如下：\n"
                "  - title：作用（字符串）\n"
                "  - script：纯代码（字符串，不要包裹解释器调用命令）\n"
                "  - type：python / shell / ruby 之一\n\n"
                "要求：\n"
                "- 脚本可无人值守自动执行，禁止 input()/gets/read 等交互输入，参数硬编码或用环境变量\n"
                "- 双引号须转义为 \\\""
            ),
        })
        flow_out = self.flowOutput(AEEmployeeFunction.receiveScripts)
        # AE_ANSWER 设为数组结构：每项为脚本 spec 模板（title / script / type 占位），由 LLM 填充多项
        flow_out.set_llm_out({
            AE_ANSWER: [
                {
                    AE_TITLE: llm_generate("作用（脚本用途说明）"),
                    "script": llm_generate("脚本内容（可执行的脚本文本）"),
                    "type": llm_generate("脚本类型，取值 python / shell / ruby 之一"),
                }
            ],
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        # 携带可用脚本执行环境（AEEnvParamType: python / ruby / shell）
        payload.add_env_param(AEEnvParamType.python)
        payload.add_env_param(AEEnvParamType.ruby)
        payload.add_env_param(AEEnvParamType.shell)
        self.send_llm_payload(payload)

    def receiveScripts(self, data: dict) -> bool:
        """接收 LLM 返回的多个 AEScript 任务：AE_ANSWER 已是 JSON 结构（数组），
        逐项创建 AEScript 并加入 self._flows（脚本完成回程路由回本 employee）。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <脚本目录数组>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        # AE_ANSWER 已是 JSON 结构（数组），直接使用；非数组则告警并打印数据
        if isinstance(result, list):
            specs = result
        else:
            logger.warning(
                "[AEEmployee:%s] AE_ANSWER 非数组，跳过脚本生成，收到数据: %r",
                self.ident, result,
            )
            specs = []
        # 为每个 spec 创建 AEScript 并加入 self._flows
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            try:
                # 脚本完成回程 ident 填本 employee.ident，路由回本 employee
                flowOutput = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("脚本执行结果")})
                script_flow = AEScript(flowOutput=flowOutput)
                script_flow.update(spec.get(AE_TITLE, ""), spec.get("script", ""), spec.get("type", ""))
                self.addFlow(script_flow)
                logger.info(
                    "[AEEmployee:%s] 添加 AEScript 子 flow: title=%r type=%r",
                    self.ident, script_flow.title, script_flow.type,
                )
            except (ValueError, TypeError) as e:
                logger.warning("[AEEmployee:%s] 跳过非法脚本 spec=%r: %s", self.ident, spec, e)
        # 启动首个脚本执行（其余脚本由 receive_flow_result 在前一个完成后逐个推进）
        first_script = self.nextFlow()
        if first_script is not None:
            first_script.startFlow(AEFlowInput(content=""))
            logger.info("[AEEmployee:%s] 启动首个 AEScript 执行: title=%r", self.ident, first_script.title)
        else:
            logger.warning("[AEEmployee:%s] 无可执行的 AEScript", self.ident)
        return True
