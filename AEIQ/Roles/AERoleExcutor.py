"""
AERoleExcutor - 角色执行 Flow，继承 AERole。

承担"角色信息生成 → 问题优化 → 目标拆解 → (原子)执行类型判定 → 脚本/直接作答"的执行链：
  startFlow → requestRoleInformation → receiveRoleInfomation → requestOptimizeInput
  → receiveOptimizeInput → requestDecompose → receiveDecompose
    ├─ 可拆解：为每个子任务创建 AERoleExcutor subFlow（递归拆解，全部完成后汇总）
    └─ 已原子：requestQuestionType → receiveQuestionType
        ├─ script：requestScripts → receiveScripts（生成并执行 AEScript 子 flow）
        └─ llm：requestDirectAnswer（直接由 LLM 作答完成 flow）

由需要"按问题类型分流到脚本或直接作答"的角色继承（如 AEEmployee）。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_TITLE, AE_ANSWER, AE_CONFIRM
from Context.Context.AELLMPayload import AELLMPayload, AEEnvParamType, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Tools.Scrips import AEScript
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole
from Roles.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleExcutorFunction(AEFunctional):
    """角色执行 Flow 专属回包功能性方法名（继承 AEFunctional 的 flow_receive_* 常量，可按需扩展）。"""
    receiveDecompose = "receiveDecompose"        # 接收 LLM 将目标拆解出的更小角色任务列表，传入 map
    receiveQuestionType = "receiveQuestionType"  # 接收 LLM 判定的问题处理类型（script / llm），传入 map
    receiveScripts = "receiveScripts"            # 接收 LLM 返回的多个 AEScript 任务，传入 map


class AERoleExcutor(AERole):
    """角色执行 Flow：串行角色信息→问题优化→目标拆解→(原子)执行类型判定→脚本/直接作答。

    单一类承担 expert/workgroup/employee 等角色：由 self.role(AEFlowRole) 标记当前扮演的角色，
    由 receiveDecompose 在创建 subFlow 时设定。
    """

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        # 问题处理类型判定结果（script / llm）：由 receiveQuestionType 赋值
        self._questionType: str = ""
        # 当前扮演的角色（AEFlowRole）：由上游 receiveDecompose 创建本 flow 时设定，默认 employee
        self.role: AEFlowRole = AEFlowRole.employee

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，串行 requestRoleInformation → requestOptimizeInput 后再执行实际任务。

        Args:
            flowInput: flow 输入数据（content 即上游下发的子任务）
        """
        if not super().startFlow(flowInput):
            logger.warning("[AERoleExcutor:%s] startFlow 失败：基类未启动（非 default 状态），忽略", self.ident)
            return
        # 先请求 LLM 生成自身工作名称与能力范围（回包走 receiveRoleInfomation，再 requestOptimizeInput）
        self.requestRoleInformation()

    def receiveRolePrompt(self, data: dict) -> bool:
        """接收 rolePrompt 后，请求生成问题优化提示（requestOptimizeInput）。"""
        result = super().receiveRolePrompt(data)
        # rolePrompt 生成后，交 LLM 生成问题优化提示（回包走 receiveOptimizeInput）
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题（AE_ANSWER）：存入 optimizePromptResult，再请求判定执行类型（requestQuestionType）。

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
            logger.info("[AERoleExcutor:%s] 收到需确认信息:\n%s", self.ident, confirm)
            return True
        self.optimizePromptResult = result or ""
        logger.info("[AERoleExcutor:%s] 收到优化后的问题:\n%s", self.ident, self.optimizePromptResult)
        # 先将目标与任务拆解为更小的角色任务并创建 subFlow（receiveDecompose）；拆到原子再走脚本/直接作答
        self.requestDecompose()
        return True

    def requestDecompose(self) -> None:
        """按层级向下分解：请求 LLM 将目标拆解为子任务，每个子任务可分配给**当前角色以下任一层级**
        （roles_below(self.role)），而非仅下一层。已到最底层(task)则不再拆解，直接 requestQuestionType 执行。

        层级：expert > workgroup > employee > task（原子）。
        - expert 可拆给 workgroup / employee / task；workgroup 可拆给 employee / task；employee 只能拆给 task。
        - messages: system(role_brief) / system(目标，AE_USER_QUESTION_PREFIX 前缀) / system(可选下层角色清单) / user(拆解+选层指令)
        - out_schema: {tasks 数组占位}，每项 {title, task, role}；role 从下层中选；已原子则空数组 []
        - 走 receiveDecompose：回包后按每项 role 创建 AERoleExcutor/AETask subFlow 并启动；
          为空则该目标已原子，转 requestQuestionType 走脚本/直接作答
        """
        from Roles.AERoleType import roles_below, ROLE_PARAMS  # 懒导入避免循环
        below = roles_below(self.role)
        if not below:
            # 已到最底层（task）：不再拆解，直接执行
            logger.info("[AERoleExcutor:%s] role=%s 已为最底层，转执行类型判定（脚本/直接作答）", self.ident, self.role.value)
            self.requestQuestionType()
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 目标以统一前缀标明，作为 system 消息
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.optimizePromptResult}",
        })
        # 可选下层角色清单（当前角色以下所有层级）
        role_lines = []
        for r in below:
            info = ROLE_PARAMS.get(r)
            if info is not None:
                role_lines.append(f"- type: {r.value}；职称：{info.title}；职责：{info.responsibility}")
            else:
                role_lines.append(f"- type: {r.value}；原子任务（task），不再拆解，直接执行")
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: "可选下层角色（为每个子任务选最合适的一个 type）：\n" + "\n".join(role_lines),
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请将{AE_USER_QUESTION_PREFIX}这一目标与任务拆解为可独立完成的子任务，"
                "并为每个子任务从上述下层角色中选择最合适的执行层级。"
                "在 tasks 中列出，每项含 title（任务标题）、task（任务内容，可独立完成）、role（从上述 type 中选）；"
                "若该目标已足够原子、无需进一步拆解，返回空数组 []。"
            ),
        })
        logger.info("[AERoleExcutor:%s] role=%s → 拆解，可选下层: %s", self.ident, self.role.value, [r.value for r in below])
        flow_out = self.flowOutput(AERoleExcutorFunction.receiveDecompose)
        flow_out.set_llm_out({
            "tasks": [
                {
                    AE_TITLE: llm_generate("任务标题"),
                    "task": llm_generate("任务内容，可独立完成"),
                    "role": llm_generate("执行角色 type，从可选下层中选"),
                }
            ]
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveDecompose(self, data: dict) -> bool:
        """接收 LLM 拆解出的子任务及所选层级：非空则按每项 role 创建对应 subFlow（AETask 或 AERoleExcutor）
        并启动；为空或已到最底层则转 requestQuestionType 走脚本/直接作答。

        role 必须在 roles_below(self.role) 中；非法/缺失时回退到下一层（below[0]）。

        Args:
            data: 回包内层 llm_out，形如 {"tasks": [{title, task, role}, ...]} 或字符串数组；空数组表示已原子

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        from Roles.AERoleType import roles_below  # 懒导入避免循环
        from Roles.AETask import AETask  # 懒导入避免循环
        below = roles_below(self.role)
        if not below:
            # 已到最底层：不应再拆解，直接执行
            self.requestQuestionType()
            return True
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if tasks is None and isinstance(data, str):
            tasks = [tasks] if tasks.strip() else []
        elif not isinstance(tasks, list):
            tasks = []
        if not tasks:
            logger.info("[AERoleExcutor:%s] 目标已原子，转执行类型判定（脚本/直接作答）", self.ident)
            self.requestQuestionType()
            return True
        # 拆解出子任务：按每项 role 创建对应 subFlow
        below_set = set(below)
        default_role = below[0]  # 回退到下一层
        for spec in tasks:
            if isinstance(spec, str):
                content = spec
                role_enum = default_role
            elif isinstance(spec, dict):
                content = spec.get("task") or spec.get(AE_TITLE) or ""
                role_str = (spec.get("role") or "").strip()
                try:
                    role_enum = AEFlowRole(role_str)
                except ValueError:
                    role_enum = default_role
            else:
                continue
            if role_enum not in below_set:
                logger.warning("[AERoleExcutor:%s] 子任务 role=%r 不在可选下层内，回退 %s",
                               self.ident, role_enum.value, default_role.value)
                role_enum = default_role
            content = str(content or "")
            if role_enum == AEFlowRole.task:
                sub = AETask(
                    flowOutput=AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("任务结论")}),
                )
            else:
                sub = AERoleExcutor(
                    flowOutput=AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("任务结论")}),
                )
                sub.role = role_enum
            self.addFlow(sub)
            sub.startFlow(AEFlowInput(content=content))
            logger.info(
                "[AERoleExcutor:%s] 创建 subFlow(role=%s): ident=%s | 子任务=%s",
                self.ident, role_enum.value, sub.ident, content,
            )
        return True

    def requestQuestionType(self) -> None:
        """请求 LLM 判定当前优化后的问题是否需要脚本程序处理。

        - messages: system(role_brief) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(判定指令)
        - out_schema: {result 占位}，由 LLM 填充 "script" 或 "llm"
        - 走 receiveQuestionType：回包后据 result 决定走脚本流程或直接由 LLM 作答
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
                "script（需要脚本）或 llm（不需要脚本，直接由 LLM 作答）。"
            ),
        })
        flow_out = self.flowOutput(AERoleExcutorFunction.receiveQuestionType)
        flow_out.set_llm_out({"result": llm_generate("script 或 llm")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveQuestionType(self, data: dict) -> bool:
        """接收 LLM 判定结果（result: script / llm），据结果分流。

        - script：走 requestScripts 生成并执行脚本。
        - llm：无需脚本，直接由 LLM 作答完成。

        Args:
            data: 回包内层 llm_out，形如 {"result": <script / llm>}；若直接为字符串则视为 result 值

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = data.get("result") if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        result = (result or "").strip().lower()
        self._questionType = result
        logger.info("[AERoleExcutor:%s] 问题类型判定: result=%s", self.ident, result)
        if result == "script":
            # 需要脚本：以优化后的问题请求生成并执行脚本
            self.requestScripts(self.optimizePromptResult)
            return True
        # llm：无需脚本，直接请求 LLM 对优化后的问题给出结论
        self.requestDirectAnswer()
        return True

    def requestDirectAnswer(self) -> None:
        """无需脚本时，直接请求 LLM 对优化后的问题给出结论。

        - messages: system(role_brief) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(直接作答指令)
        - out_schema: 走 flow_receive_complete，回包直接完成本 flow（outResult 取 self.output.out_schema，含 AE_ANSWER）
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
        # 走 flow_receive_complete：回包直接完成本 flow
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def requestScripts(self, question: str) -> None:
        """以传入的问题（当前 AE_ANSWER）请求 LLM 生成多个 AEScript 任务。

        - messages: system(role_brief) / system(问题，AE_USER_QUESTION_PREFIX 前缀) / user(生成脚本任务指令)
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
        flow_out = self.flowOutput(AERoleExcutorFunction.receiveScripts)
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
        逐项创建 AEScript 并加入 self._flows（脚本完成回程路由回本 flow）。

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
                "[AERoleExcutor:%s] AE_ANSWER 非数组，跳过脚本生成，收到数据: %r",
                self.ident, result,
            )
            specs = []
        # 为每个 spec 创建 AEScript 并加入 self._flows
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            try:
                # 脚本完成回程 ident 填本 flow.ident，路由回本 flow
                flowOutput = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("脚本执行结果")})
                script_flow = AEScript(flowOutput=flowOutput)
                script_flow.update(spec.get(AE_TITLE, ""), spec.get("script", ""), spec.get("type", ""))
                self.addFlow(script_flow)
                logger.info(
                    "[AERoleExcutor:%s] 添加 AEScript 子 flow: title=%r type=%r",
                    self.ident, script_flow.title, script_flow.type,
                )
            except (ValueError, TypeError) as e:
                logger.warning("[AERoleExcutor:%s] 跳过非法脚本 spec=%r: %s", self.ident, spec, e)
        # 启动首个脚本执行（其余脚本由 receive_flow_result 在前一个完成后逐个推进）
        first_script = self.nextFlow()
        if first_script is not None:
            first_script.startFlow(AEFlowInput(content=""))
            logger.info("[AERoleExcutor:%s] 启动首个 AEScript 执行: title=%r", self.ident, first_script.title)
        else:
            logger.warning("[AERoleExcutor:%s] 无可执行的 AEScript", self.ident)
        return True
