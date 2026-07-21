"""
AEWorkGroup - 工作组 Flow，继承 AERole。

负责完成一个维度 / 目录的目标：接收上游分配的维度目标，
驱动该维度的工作并输出结果。各工作组相互独立，可并行。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_TITLE, AE_ANSWER, AE_CONFIRM
from WorkFlows.AEFlowInterfaceImpl import AEFlowInterfaceImpl
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERole import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT
from Roles.AEBaseRole import AERole

logger = logging.getLogger(__name__)


class AEWorkGroupFunctional(AEFunctional):
    """工作组 Flow 专属回包功能性方法名（继承 AEFunctional 的 flow_receive_* 常量，可按需扩展）。"""
    receiveEmployees = "receiveEmployees"  # 接收 LLM 返回的多个 employee 任务，传入 map


class AEWorkGroup(AERole):
    """工作组 Flow：完成单一维度 / 目录的目标。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "Work Group"
        self.responsibility = (
            "负责完成分配给本工作组的一个维度 / 目录目标。\n"
            "要求：\n"
            "1. 仅处理本维度范围内的工作，不越界。\n"
            "2. 输出该维度的结论与产物。\n"
            "3. 与其他工作组保持独立，可并行。"
        )

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，先 requestRoleInformation 生成自身 title/能力，回包 receiveRoleInfomation 后再执行实际任务。

        Args:
            flowInput: flow 输入数据（content 即本工作组负责的维度目标）
        """
        if not super().startFlow(flowInput):
            return
        # 先请求 LLM 生成自身工作名称与能力范围（回包走 receiveRoleInfomation，再发送实际任务）
        self.requestRoleInformation()

    def receiveRoleInfomation(self, data: dict) -> bool:
        """接收 title/responsibility 后，请求生成问题优化提示（requestOptimizeInput）。"""
        result = super().receiveRoleInfomation(data)
        # title/responsibility 生成后，交 LLM 生成问题优化提示（回包走 receiveOptimizeInput）
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题（AE_ANSWER）：交基类存储为 optimizePromptResult，再请求创建多个 employee。

        覆写基类：基类负责提取 AE_ANSWER 并存入 self.optimizePromptResult；
        本类在此基础上处理确认信息并调用 requestEmployees。

        - AE_ANSWER 非空：优化后的问题（最优问题），由基类存入 optimizePromptResult，并调用 requestEmployees。
        - AE_CONFIRM 非空：需提问者确认的信息（此时 AE_ANSWER 为空），仅记录。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <优化后的问题>, AE_CONFIRM: <需确认信息>}（二选一）

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        # 基类负责提取 AE_ANSWER 并存入 self.optimizePromptResult
        result = super().receiveOptimizeInput(data)
        # WorkGroup 专属：处理确认信息 + 请求创建 employee
        confirm = data.get(AE_CONFIRM) if isinstance(data, dict) else None
        confirm = (confirm or "").strip() if isinstance(confirm, str) else ""
        if confirm:
            logger.info("[AEWorkGroup:%s] 收到需确认信息:\n%s", self.ident, confirm)
            return result
        # 收到最优问题后，请求创建多个 employee
        self.requestEmployees(self.optimizePromptResult)
        return result

    def requestEmployees(self, question: str) -> None:
        """以传入的问题（最优问题）请求 LLM 生成多个 employee 任务。

        - messages: system(role_brief) / system(问题 + AE_USER_QUESTION_PREFIX) / user(生成 employee 任务指令)
        - out_schema: {AE_ANSWER: employee 任务 JSON 数组 占位}，由 LLM 填充
        - 走 receiveEmployees：回包后由 receiveEmployees 解析为 AEEmployee 列表并加入 self._flows

        Args:
            question: 当前最优问题（AE_ANSWER）
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
                "请针对上述问题生成多个可独立执行的员工任务，严格输出 JSON 数组，每项结构如下：\n"
                " title：任务标题（简述员工负责的工作，字符串）\n"
                " task：任务内容（交给员工执行的具体任务描述，包含任务必要的上下文"
            ),
        })
        flow_out = self.flowOutput(AEWorkGroupFunctional.receiveEmployees)
        # AE_ANSWER 设为数组结构：每项为 employee 任务模板（title / task 占位）
        flow_out.set_llm_out({
            AE_ANSWER: [
                {
                    AE_TITLE: llm_generate("任务标题（简述员工负责的工作）"),
                    "task": llm_generate("任务内容（交给员工执行的具体任务描述和任务必要的上下文）"),
                }
            ],
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveEmployees(self, data: dict) -> bool:
        """接收 LLM 返回的多个 employee 任务：AE_ANSWER 已是 JSON 结构（数组），
        逐项创建 AEEmployee 并加入 self._flows（employee 完成回程路由回本 workgroup）。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <employee 任务数组>}

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
                "[AEWorkGroup:%s] AE_ANSWER 非数组，跳过 employee 创建，收到数据: %r",
                self.ident, result,
            )
            specs = []
        # 为每个 spec 创建 AEEmployee 并加入 self._flows
        from Roles.Employee.AEEmployee import AEEmployee  # 懒导入避免循环
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            try:
                # employee 完成回程 ident 填本 workgroup.ident，路由回本 workgroup
                flowOutput = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("员工结论")})
                employee = AEEmployee(flowOutput=flowOutput)
                AEFlowInterfaceImpl.addFlow(self, employee)
                task = spec.get("task", "") or spec.get(AE_TITLE, "")
                logger.info(
                    "[AEWorkGroup:%s] 添加 AEEmployee 子 flow: title=%r task=%r",
                    self.ident, spec.get(AE_TITLE, ""), task,
                )
            except Exception as e:
                logger.warning("[AEWorkGroup:%s] 跳过非法 employee spec=%r: %s", self.ident, spec, e)
        # 启动首个 employee 执行（其余由 receive_flow_result 在前一个完成后逐个推进）
        first_employee = self.nextFlow()
        if first_employee is not None:
            # 取首个 spec 的 task 作为 input.content
            first_task = ""
            if specs and isinstance(specs[0], dict):
                first_task = specs[0].get("task", "") or specs[0].get(AE_TITLE, "")
            first_employee.startFlow(AEFlowInput(content=first_task))
            logger.info("[AEWorkGroup:%s] 启动首个 AEEmployee: title=%r", self.ident, getattr(first_employee, AE_TITLE, ""))
        else:
            logger.warning("[AEWorkGroup:%s] 无可执行的 AEEmployee", self.ident)
        return True
