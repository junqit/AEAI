"""AETask - 任务级执行能力 mixin。

提供 requestQuestionType / receiveQuestionType / requestDirectAnswer / requestScripts / receiveScripts：
原子任务的执行能力（脚本/直接作答）。AERoleExcutor 继承本 mixin 获得执行能力。
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
    """任务级执行能力：脚本/直接作答。"""

    def requestQuestionType(self) -> None:
        """请求 LLM 判定当前优化后的问题是否需要脚本程序处理。"""
        from Roles.AERoleExcutor import AERoleExcutorFunction
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: _REALTIME_DATA_NOTE,
        })
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
        """接收 LLM 判定结果（result: script / llm），据结果分流。"""
        result = data.get("result") if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        result = (result or "").strip().lower()
        self._questionType = result
        if result == "script":
            self.requestScripts(self.optimizePromptResult)
            return True
        self.requestDirectAnswer()
        return True

    def requestDirectAnswer(self) -> None:
        """无需脚本时，直接请求 LLM 对优化后的问题给出结论。"""
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: _REALTIME_DATA_NOTE,
        })
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.optimizePromptResult}",
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"请直接回答{AE_USER_QUESTION_PREFIX}，给出准确、完整的结论。",
        })
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def requestScripts(self, question: str) -> None:
        """以传入的问题请求 LLM 生成多个 AEScript 任务。"""
        from Roles.AERoleExcutor import AERoleExcutorFunction
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: _REALTIME_DATA_NOTE,
        })
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
                "- 双引号须转义为 \\\"\n"
                "- 需联网获取数据时，使用国内可访问的服务器地址，避免使用国内无法直接访问的境外 API"
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
            logger.warning("[%s][%s][d=%s] AE_ANSWER 非数组，跳过脚本生成，收到数据: %r", type(self).__name__, self.title, self.deepth, result)
            specs = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            try:
                flowOutput = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("脚本执行结果")})
                script_flow = AEScript(flowOutput=flowOutput)
                script_flow.update(spec.get(AE_TITLE, ""), spec.get("script", ""), spec.get("type", ""))
                self.addFlow(script_flow)
                logger.info("[%s][%s][d=%s] 添加 AEScript 子 flow: title=%r type=%r",
                            type(self).__name__, self.title, self.deepth, script_flow.title, script_flow.type)
            except (ValueError, TypeError) as e:
                logger.warning("[%s][%s][d=%s] 跳过非法脚本 spec=%r: %s", type(self).__name__, self.title, self.deepth, spec, e)
        first_script = self.nextFlow()
        if first_script is not None:
            first_script.startFlow(AEFlowInput(content=""))
            logger.info("[%s][%s][d=%s] 启动首个 AEScript 执行: title=%r", type(self).__name__, self.title, self.deepth, first_script.title)
        else:
            logger.warning("[%s][%s][d=%s] 无可执行的 AEScript", type(self).__name__, self.title, self.deepth)
        return True
