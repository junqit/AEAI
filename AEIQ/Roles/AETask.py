"""AETask - 任务级执行能力 mixin。

执行流程：
  requestQuestionType → receiveQuestionType
    ├─ llm → requestDirectAnswer（直接作答）
    └─ script → requestTaskAnalysis → receiveTaskAnalysis
                   → requestTaskPlan → receiveTaskPlan
                   → requestScripts → receiveScripts（生成并执行 AEScript）

  Task Analyzer：分析任务需要什么能力（联网/本地文件/浏览器/Shell/Python/Ruby）
  Task Planner：据分析结果确定执行方式（local/api/crawler/hybrid）
  Script Generator：据分析+计划生成对应脚本
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_TITLE, AE_ANSWER, AE_CONFIRM
from Context.Context.AELLMPayload import AELLMPayload, AEEnvParamType, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Tools.Scrips import AEScript
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT

logger = logging.getLogger(__name__)

# 脚本生成时的只读约束 + 本地文件性质 + 实时数据引导
_REALTIME_DATA_NOTE = (
    "所有目录下的内容只可读取，不可进行任何修改、删除或写入操作。\n"
    "本地文件系统仅含工程文件（代码 / 配置 / 文档等），不含任何网络实时数据。\n"
    "凡涉及外部实时或动态数据——如新闻资讯、天气、股价行情、汇率、赛事比分、"
    "热搜榜单、物流状态、实时价格等——一律通过编写脚本联网获取，"
    "严禁尝试读取本地文件来获取这类数据（本地根本没有）。\n"
    "本地信息不完整时，优先使用脚本程序获取网络实时数据进行分析。"
)


class AETaskMixin:
    """任务级执行能力：Task Analyzer → Task Planner → Script Generator。"""

    def requestQuestionType(self) -> None:
        """请求 LLM 判定当前优化后的问题是否需要脚本程序处理。"""
        from Roles.AERoleExcutor import AERoleExcutorFunction
        messages = self._build_base_messages()
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
        """接收 LLM 判定结果（result: script / llm），据结果分流。"""
        result = data.get("result") if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        result = (result or "").strip().lower()
        self._questionType = result
        if result == "script":
            self.requestTaskAnalysis()
            return True
        self.requestDirectAnswer()
        return True

    # ==================== Task Analyzer ====================

    def requestTaskAnalysis(self) -> None:
        """请求 LLM 分析任务需要哪些能力（联网/本地文件/浏览器/Shell/Python/Ruby）。"""
        from Roles.AERoleExcutor import AERoleExcutorFunction
        messages = self._build_base_messages()
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请分析{AE_USER_QUESTION_PREFIX}这一任务需要哪些能力，逐项判断并填入对应字段（true/false）：\n"
                "  - needs_network：是否需要联网获取数据\n"
                "  - needs_local_file：是否需要读取本地文件\n"
                "  - needs_browser：是否需要浏览器渲染（JS 动态页面）\n"
                "  - needs_shell：是否需要 Shell 命令\n"
                "  - needs_python：是否需要 Python 计算/分析\n"
                "  - needs_ruby：是否需要 Ruby 处理\n"
                "  - analysis：简要说明判断依据\n"
                "严格输出上述 JSON 结构。"
            ),
        })
        flow_out = self.flowOutput(AERoleExcutorFunction.receiveTaskAnalysis)
        flow_out.set_llm_out({
            "needs_network": llm_generate("true 或 false"),
            "needs_local_file": llm_generate("true 或 false"),
            "needs_browser": llm_generate("true 或 false"),
            "needs_shell": llm_generate("true 或 false"),
            "needs_python": llm_generate("true 或 false"),
            "needs_ruby": llm_generate("true 或 false"),
            "analysis": llm_generate("判断依据说明"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveTaskAnalysis(self, data: dict) -> bool:
        """接收任务能力分析结果，存入 self._taskAnalysis，进入 Task Planner。"""
        if not isinstance(data, dict):
            data = {}
        self._taskAnalysis = {
            "needs_network": str(data.get("needs_network", "")).strip().lower() == "true",
            "needs_local_file": str(data.get("needs_local_file", "")).strip().lower() == "true",
            "needs_browser": str(data.get("needs_browser", "")).strip().lower() == "true",
            "needs_shell": str(data.get("needs_shell", "")).strip().lower() == "true",
            "needs_python": str(data.get("needs_python", "")).strip().lower() == "true",
            "needs_ruby": str(data.get("needs_ruby", "")).strip().lower() == "true",
            "analysis": data.get("analysis", ""),
        }
        self.requestTaskPlan()
        return True

    # ==================== Task Planner ====================

    def requestTaskPlan(self) -> None:
        """请求 LLM 根据任务分析结果确定执行方式（local/api/crawler/hybrid）。"""
        from Roles.AERoleExcutor import AERoleExcutorFunction
        messages = self._build_base_messages()
        # 注入任务分析结果
        analysis = self._taskAnalysis
        analysis_text = (
            f"任务能力分析结果：\n"
            f"  需要联网: {analysis['needs_network']}\n"
            f"  需要本地文件: {analysis['needs_local_file']}\n"
            f"  需要浏览器: {analysis['needs_browser']}\n"
            f"  需要Shell: {analysis['needs_shell']}\n"
            f"  需要Python: {analysis['needs_python']}\n"
            f"  需要Ruby: {analysis['needs_ruby']}\n"
            f"  分析说明: {analysis['analysis']}\n"
        )
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: analysis_text})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据以上任务能力分析，确定执行方式并填入字段：\n"
                "  - approach：执行方式，取值之一：\n"
                "    local（纯本地操作：文件读取、数据分析、格式转换等）\n"
                "    api（直接调用公开 API 获取数据）\n"
                "    crawler（爬虫方式抓取网页数据，适用于需要登录或无公开 API 的场景）\n"
                "    hybrid（组合多种方式）\n"
                "  - plan：执行计划说明（用什么工具、分几步、每步做什么）\n"
                "  - steps：步骤列表（每项为一个可独立执行的脚本任务描述）\n"
                "严格输出上述 JSON 结构。"
            ),
        })
        flow_out = self.flowOutput(AERoleExcutorFunction.receiveTaskPlan)
        flow_out.set_llm_out({
            "approach": llm_generate("local / api / crawler / hybrid 之一"),
            "plan": llm_generate("执行计划说明"),
            "steps": [llm_generate("可独立执行的脚本任务描述")],
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveTaskPlan(self, data: dict) -> bool:
        """接收执行计划，存入 self._taskPlan，进入 Script Generator。"""
        if not isinstance(data, dict):
            data = {}
        self._taskPlan = {
            "approach": data.get("approach", ""),
            "plan": data.get("plan", ""),
            "steps": data.get("steps", []) if isinstance(data.get("steps"), list) else [],
        }
        self.requestScripts(self.optimizePromptResult)
        return True

    # ==================== Script Generator ====================

    def requestDirectAnswer(self) -> None:
        """无需脚本时，直接请求 LLM 对优化后的问题给出结论。"""
        messages = self._build_base_messages()
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"请直接回答{AE_USER_QUESTION_PREFIX}，给出准确、完整的结论。",
        })
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def requestScripts(self, question: str) -> None:
        """根据任务分析+执行计划，请求 LLM 生成对应的脚本任务。"""
        from Roles.AERoleExcutor import AERoleExcutorFunction
        messages = self._build_base_messages()
        # 注入任务分析与执行计划
        analysis = getattr(self, "_taskAnalysis", {})
        plan = getattr(self, "_taskPlan", {})
        context = (
            f"任务能力分析：{analysis.get('analysis', '')}\n"
            f"执行方式：{plan.get('approach', '')}\n"
            f"执行计划：{plan.get('plan', '')}\n"
        )
        if context.strip():
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: context})
        # 执行方式对应的脚本生成指令
        approach = plan.get("approach", "").strip().lower()
        approach_hint = {
            "local": "本任务为本地操作，直接使用文件读取、数据分析等脚本完成。",
            "api": "本任务通过调用公开 API 获取数据，注意处理认证、错误重试与响应解析。",
            "crawler": "本任务使用爬虫方式获取数据（requests + BeautifulSoup/lxml），注意多数网站需要登录，"
                       "需处理 Cookie/Session/UA 伪装；使用国内可访问的地址。",
            "hybrid": "本任务组合多种方式，按执行计划分步生成脚本。",
        }.get(approach, "")
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据以上分析与计划生成多个可独立执行的脚本任务，严格输出 JSON 数组，每项结构如下：\n"
                "  - title：作用（字符串）\n"
                "  - script：纯代码（字符串，不要包裹解释器调用命令）\n"
                "  - type：python / shell / ruby 之一\n\n"
                "要求：\n"
                "- 脚本可无人值守自动执行，禁止 input()/gets/read 等交互输入，参数硬编码或用环境变量\n"
                "- 双引号须转义为 \\\"\n"
                + (f"- {approach_hint}\n" if approach_hint else "")
                + "- 需联网获取数据时优先使用爬虫方式（如 requests + BeautifulSoup / lxml），"
                  "因多数网站需要登录，直接调用 API 可能失败；使用国内可访问的服务器地址，避免境外 API"
            ),
        })
        flow_out = self.flowOutput(AERoleExcutorFunction.receiveScripts)
        flow_out.set_llm_out({
            AE_ANSWER: [{
                AE_TITLE: llm_generate("作用（脚本用途说明）"),
                "script": llm_generate("脚本内容（可执行的脚本文本）"),
                "type": llm_generate("脚本类型，取值 python / shell / ruby 之一"),
            }]
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        payload.add_env_param(AEEnvParamType.python)
        payload.add_env_param(AEEnvParamType.ruby)
        payload.add_env_param(AEEnvParamType.shell)
        self.send_llm_payload(payload)

    def receiveScripts(self, data: dict) -> bool:
        """接收 LLM 返回的多个 AEScript 任务，逐项创建并加入 self._flows。"""
        result = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        if isinstance(result, list):
            specs = result
        else:
            logger.warning("[%s][%s][d=%s] AE_ANSWER 非数组，跳过脚本生成", type(self).__name__, self.title, self.deepth)
            specs = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            try:
                flowOutput = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("脚本执行结果")})
                script_flow = AEScript(flowOutput=flowOutput)
                script_flow.update(spec.get(AE_TITLE, ""), spec.get("script", ""), spec.get("type", ""))
                self.addFlow(script_flow)
                logger.info("[%s][%s][d=%s] 添加 AEScript: title=%r type=%r",
                            type(self).__name__, self.title, self.deepth, script_flow.title, script_flow.type)
            except (ValueError, TypeError) as e:
                logger.warning("[%s][%s][d=%s] 跳过非法脚本 spec=%r: %s", type(self).__name__, self.title, self.deepth, spec, e)
        first_script = self.nextFlow()
        if first_script is not None:
            first_script.startFlow(AEFlowInput(content=""))
            logger.info("[%s][%s][d=%s] 启动首个 AEScript: title=%r", type(self).__name__, self.title, self.deepth, first_script.title)
        else:
            logger.warning("[%s][%s][d=%s] 无可执行的 AEScript", type(self).__name__, self.title, self.deepth)
        return True

    # ==================== 辅助 ====================

    def _build_base_messages(self) -> list:
        """构建公共 messages：role_brief + 实时数据提醒 + 用户问题。"""
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: _REALTIME_DATA_NOTE})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.optimizePromptResult}",
        })
        return messages
