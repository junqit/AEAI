"""AETaskRole - 原子任务角色执行 Flow（继承 AERoleExcutor，_role()=task）。

task 为最底层执行单元：角色目标就绪后直接分解为脚本任务完成目标（必须完成；
roleGoal 为空由 AERoleExcutor.receiveOptimizeInput 错误完成，脚本为空由 receiveScripts 错误完成）。
脚本生成与执行能力（Script Generator）在本类实现。
"""
import logging

from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_ANSWER, AE_TITLE
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Context.Context.AELLMPayload import AELLMPayload, AEEnvParamType, llm_generate
from Tools.Scrips import AEScript
from Roles.AERoleType import AEFlowRole, AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT
from Roles.Defs.AERoleExcutor import AERoleExcutor

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

# 解决用户问题的强约束：不得拒绝/推诿，需外部数据须脚本获取
_SOLVE_GOAL_NOTE = (
    "你必须切实解决用户的问题或目标，不得给出无法解决、拒绝或推诿的答案。"
    "若需外部数据（网络数据、实时信息等），须通过编写脚本获取后再作答，"
    "不得以无法获取数据为由拒绝回答。"
)


class AETaskRoleFunction(AEFunctional):
    """task 角色 Flow 专属回包功能性方法名。"""
    receiveQuestionType = "receiveQuestionType"
    receiveScripts = "receiveScripts"


class AETaskRole(AERoleExcutor):
    """原子任务执行 Flow：将角色目标分解为脚本任务完成（必须完成，不完成以错误完成闭环）。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.task

    def requestRoleSelect(self) -> None:
        """task：不选角色，直接分解为脚本完成任务目标（必须完成；脚本为空时 receiveScripts 以错误完成闭环）。"""
        self.requestScripts(self.roleGoal)

    # ==================== task 执行能力（Script Generator）====================

    def requestQuestionType(self) -> None:
        """请求 LLM 判定当前优化后的问题是否需要脚本程序处理。"""
        messages = self._build_base_messages()
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请判定{AE_USER_QUESTION_PREFIX}是否需要通过编写并执行脚本程序"
                "（python / shell / ruby）来处理，并将判定结果填入 result 字段："
                "script（需要脚本）或 llm（不需要脚本，直接由 LLM 作答）。"
            ),
        })
        flow_out = self.generateFlowOutput(AETaskRoleFunction.receiveQuestionType)
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
            self.requestScripts(self.roleGoal)
            return True
        # 非 script：task 须通过脚本完成，不直答，以错误完成闭环
        logger.warning("[%s][d=%s] task 判定为非脚本（%r），以错误完成", self.title, self.deepth, result)
        self.flow_receive_complete(
            {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "task 须通过脚本完成"},
            AEFlowCompletEvent.error,
        )
        return True

    def requestScripts(self, question: str) -> None:
        """请求 LLM 生成对应的脚本任务。"""
        messages = self._build_base_messages()
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据以上信息生成多个可独立执行的脚本任务，严格输出 JSON 数组，每项含：\n"
                "  - title：作用\n"
                "  - script：纯代码，不要包裹解释器调用命令\n"
                "  - type：python / shell / ruby 之一\n\n"
                "执行环境：python 用 python -c、shell 用 sh -c、ruby 用 ruby -e，\n"
                "脚本内容原样传入解释器，stdout 作为结果返回，30 秒超时，macOS 下全只读沙箱。\n\n"
                "要求：\n"
                "- 必须完成目标，不可不完成：脚本须切实解决目标问题，不得拒绝、推诿或遗漏关键环节\n"
                "- 可无人值守执行，禁止交互输入（input/gets/read），参数硬编码或用环境变量\n"
                "- 只读沙箱执行，禁止写文件（创建/修改/删除、open 写模式、> / >> 重定向等），中间结果用 stdout 输出\n"
                + "- 联网获取数据优先用爬虫，使用国内可访问的地址，避免境外 API"
            ),
        })
        flow_out = self.generateFlowOutput(AETaskRoleFunction.receiveScripts)
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
            logger.warning("[%s][d=%s] AE_ANSWER 非数组，跳过脚本生成", self.title, self.deepth)
            specs = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            try:
                flowOutput = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("脚本执行结果")})
                script_flow = AEScript(flowOutput=flowOutput)
                script_flow.update(spec.get(AE_TITLE, ""), spec.get("script", ""), spec.get("type", ""))
                self.add_flow(script_flow)
            except (ValueError, TypeError) as e:
                logger.warning("[%s][d=%s] 跳过非法脚本 spec=%r: %s", self.title, self.deepth, spec, e)
        first_script = self.nextFlow()
        if first_script is not None:
            first_script.receive_flow_input(AEFlowInput(content="", ident=self.ident))
            logger.info("[%s][d=%s] 启动首个 AEScript: title=%r", self.title, self.deepth, first_script.title)
        else:
            logger.warning("[%s][d=%s] 无可执行的 AEScript，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete({AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "无可执行的脚本任务（脚本生成失败或为空）"}, AEFlowCompletEvent.error)
        return True

    # ==================== 辅助 ====================

    def _build_base_messages(self) -> list:
        """构建公共 messages：解决目标强约束 + role_brief + 实时数据提醒 + 用户问题。"""
        messages = []
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: _SOLVE_GOAL_NOTE})
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: _REALTIME_DATA_NOTE})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.roleGoal}",
        })
        return messages
