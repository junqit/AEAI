"""AERoleExcuterScript - 脚本执行能力 mixin。

流程：start_flow → _request_script_type（LLM 按 ruby/python/shell 能力与已装工具包选型）→
receiveScriptType → _request_script_generate（LLM 生成脚本内容）→ receiveScriptGenerate →
_run_script（执行）→ _verify（LLM 验证评分，≥PASS_SCORE 完成；不达标 _request_script_fix 重试）。
执行失败亦经 _request_script_fix 重试，循环至通过。

目标取 input.goal；脚本内容由 LLM 生成并存于每次 attempt（AEScriptAttempt.script）；
执行记账 self.attempts 由 start_flow 初始化；outResult 由历次 attempt 组装。
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AERoleExcuterScriptFunction(AEFunctional):
    """AERoleExcuterScript 专属回包功能性方法名。"""
    receiveScriptType = "receiveScriptType"            # LLM 选脚本类型（按当前能力与已装工具包）
    receiveScriptGenerate = "receiveScriptGenerate"  # 生成脚本内容（类型已选定）
    receiveScriptFix = "receiveScriptFix"
    receiveScriptVerify = "receiveScriptVerify"


class AEScriptType(str, Enum):
    """脚本类型常量枚举"""
    python = "python"
    shell = "shell"
    ruby = "ruby"


@dataclass
class AEScriptAttempt:
    """单次执行记账：脚本内容 + 执行结果 + 验证评分（含理由）。

    stdout 与 error 互斥：执行成功记 stdout（error 空）；执行失败记 error（stdout 空）。
    score/reason 仅在执行成功且经 LLM 验证后由 receiveScriptVerify 回填到该次 attempt。
    attempt 于收到脚本时创建（receiveScriptGenerate/receiveScriptFix），执行结果与验证评分随后
    回填到同一实例；AERoleExcuterScript 不另存脚本内容，当前 attempt = self.attempts[-1]。
    last_error/pending_stdout/verified_score/verify_count 等均由历次 attempt 派生，不另存冗余字段。
    """
    script: str = ""
    stdout: str = ""
    error: str = ""
    score: Optional[int] = None
    reason: str = ""

    # 拼装本 attempt 供下次 LLM 修正请求使用的消息块（含脚本/执行结果/不达标理由）
    def to_history_message(self, index: int) -> str:
        lines = [f"—— 第 {index + 1} 次 ——", f"脚本内容:\n{self.script}"]
        if self.error:
            lines.append(f"执行结果: 执行失败 → {self.error}")
        else:
            lines.append(f"程序输出:\n{self.stdout}")
        # 不达标理由一并带入，供下次 LLM 正确认识到问题
        if self.score is not None:
            lines.append(f"评分: {self.score}/100；不达标理由: {self.reason}")
        return "\n".join(lines)

    # 解析 LLM 打分回包（score + reason）并回填到本 attempt
    def apply_verify_result(self, data: dict) -> None:
        if not isinstance(data, dict):
            data = {}
        self.score = self._parse_score(data.get("score"))
        self.reason = str(data.get("reason", "") or "")

    # 容错解析 0-100 整数分值；失败返回 0
    @staticmethod
    def _parse_score(value) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, (int, float)):
            n = int(value)
        elif isinstance(value, str):
            m = re.search(r"\d+", value)
            n = int(m.group()) if m else 0
        else:
            n = 0
        return max(0, min(100, n))


class AERoleExcuterScript:
    """脚本执行能力 mixin：仅脚本执行循环（选型→生成→执行→验证→修正）；前置链路与编排由宿主
    （AERoleExcutor）承担。目标 = 宿主 input.goal；type 由本 mixin 经 LLM 选型后贯穿执行；脚本内容
    由 LLM 生成并存于每次 attempt（AEScriptAttempt.script）。回包方法落在宿主实例上。

    流程：start_flow → _request_script_type（LLM 选型）→ receiveScriptType → _request_script_generate
    （LLM 生成内容）→ receiveScriptGenerate → _run_script（执行结果回填到当前 attempt）→
    _verify（≥PASS_SCORE 完成；不达标 _request_script_fix 重试）。执行失败亦经 _request_script_fix
    重试，循环至通过。outResult 由历次 attempt 组装（每次结果，不论对错）。

    实例执行记账：self.attempts（历次 AEScriptAttempt，含脚本/结果/评分）为信息源；由 start_flow 初始化。
    """

    VALID_TYPES = tuple(t.value for t in AEScriptType)
    PASS_SCORE = 80

    type: str = ""

    # 流程入口：初始化 attempts 后选型→生成→执行→验证循环。
    def start_flow(self) -> None:
        self.attempts = []
        self._request_script_type()

    # 请求 LLM 按能力与已装工具包选脚本类型。
    def _request_script_type(self) -> None:
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: f"目标/期望输出:\n{self.input.get_goal() or self.input.get_content() or ''}\n",
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    "请根据下方提供的当前 ruby / python / shell 能力与已安装的工具包，"
                    "选择最适合产出上述目标/期望输出的脚本类型。严格输出 JSON，含：\n"
                    "  - type：在 python / shell / ruby 中选择最适合的一种\n"
                    "  - reason：简短说明为何该类型最适合（能力 / 已装工具包匹配度）\n\n"
                    "选择依据：哪种语言的已装工具包与能力最能高效、可靠地产出目标/期望输出。"
                ),
            },
        ]
        flow_out = self.generateFlowOutput(AERoleExcuterScriptFunction.receiveScriptType)
        flow_out.set_llm_out({
            "type": llm_generate("脚本类型：python / shell / ruby 之一，按当前能力与已装工具包选最适合的"),
            "reason": llm_generate("简短理由：为何该类型最适合"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 选择脚本类型", self.title, self.deepth)
        self.flow_send_llm_request(payload)

    # 接收脚本类型，置 self.type 后请求生成内容。
    def receiveScriptType(self, data: dict) -> bool:
        type_value = data.get("type") if isinstance(data, dict) else ""
        type_value = type_value.value if isinstance(type_value, AEScriptType) else type_value
        if type_value not in self.VALID_TYPES:
            logger.warning("[%s][d=%s] 选型 type=%r 非法，默认 python", self.title, self.deepth, type_value)
            type_value = "python"
        self.type = type_value
        logger.info("[%s][d=%s] 选定脚本类型: %s", self.title, self.deepth, self.type)
        self._request_script_generate()
        return True

    # 类型已选定，请求 LLM 生成脚本内容。
    def _request_script_generate(self) -> None:
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"目标/期望输出:\n{self.input.get_goal() or self.input.get_content() or ''}\n"
                    f"脚本类型: {self.type}\n"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    f"请用 {self.type} 编写一个可独立执行的脚本，使其执行后在 stdout 产出上述目标/期望输出。"
                    "严格输出 JSON，含：\n"
                    "  - script：纯代码，不要包裹解释器调用命令\n\n"
                    "执行环境：python 用 python -c、shell 用 sh -c、ruby 用 ruby -e，"
                    "脚本内容原样传入解释器，stdout 作为结果返回，30 秒超时，macOS 下全只读沙箱。\n"
                    "要求：\n"
                    "- 必须切实解决上述目标/期望输出所指的目标与问题，不得拒绝、推诿或用占位符/伪代码绕过\n"
                    "- 不得瞎写：禁止捏造数据或结果，所需数据须真实获取或计算得出，不得用伪造值冒充目标/期望输出\n"
                    "- 可无人值守执行，禁止交互输入（input/gets/read），参数硬编码或用环境变量\n"
                    "- 只读沙箱执行，禁止写文件（创建/修改/删除、open 写模式、> / >> 重定向等），中间结果用 stdout 输出\n"
                    "- 联网获取数据优先用爬虫，使用国内可访问的地址，避免境外 API"
                ),
            },
        ]
        flow_out = self.generateFlowOutput(AERoleExcuterScriptFunction.receiveScriptGenerate)
        flow_out.set_llm_out({"script": llm_generate("可执行的脚本文本")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 生成 %s 脚本内容", self.title, self.deepth, self.type)
        self.flow_send_llm_request(payload)

    # 接收脚本内容，创建 attempt 后执行；空脚本以错误完成。
    def receiveScriptGenerate(self, data: dict) -> bool:
        script = data.get("script") if isinstance(data, dict) else None
        if script is None and isinstance(data, str):
            script = data
        script = (script or "").strip()
        if not script:
            logger.warning("[%s][d=%s] 生成脚本为空，以错误完成", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: ["脚本生成失败：LLM 未返回脚本代码"]},
                AEFlowCompletEvent.error,
            )
            return True
        self.attempts.append(AEScriptAttempt(script=script))
        self._run_script()
        return True

    # 执行当前 attempt 脚本；成功→验证，失败→修正重试。
    def _run_script(self) -> None:
        from Tools.Scrips.AEScriptRunner import get_runner
        att = self.attempts[-1]
        try:
            runner = get_runner(self.type)
            stdout = runner.run(att.script)
        except Exception as e:
            err = str(e)
            att.error = err
            logger.error("[%s][d=%s] 脚本执行失败(type=%s)，请求 LLM 修正后重试",
                         self.title, self.deepth, self.type)
            self._request_script_fix(err)
            return
        att.stdout = stdout
        logger.info("[%s][d=%s] 脚本执行成功(type=%s)", self.title, self.deepth, self.type)
        self._verify(stdout)

    # 组装出站结果：仅验证通过的成功结果。
    def _build_results(self) -> str:
        out = []
        for att in self.attempts:
            if att.score is not None and att.score >= self.PASS_SCORE:
                out.append(att.stdout)
        return "\n".join(out)

    # 以执行结果完成本 flow。
    def _complete(self) -> None:
        delegate_ident = self.delegate.ident if self.delegate is not None else self.ident
        self.flow_complete({AE_IDENT: delegate_ident, AE_CONTENT: self._build_results()})

    # 携带脚本能力与工具包信息；选型前带全部，选型后仅带选定类型。
    def _apply_script_env(self, payload) -> None:
        from Context.Context.AELLMPayload import AEEnvParamType
        payload.remove_env_param(AEEnvParamType.system)
        type_env = {
            AEScriptType.python.value: AEEnvParamType.python,
            AEScriptType.shell.value: AEEnvParamType.shell,
            AEScriptType.ruby.value: AEEnvParamType.ruby,
        }
        env = type_env.get(self.type)
        if env is None:
            # 选型前：type 未定，携带全部三种能力供 LLM 评估选型
            payload.add_env_param(AEEnvParamType.python)
            payload.add_env_param(AEEnvParamType.ruby)
            payload.add_env_param(AEEnvParamType.shell)
        else:
            payload.add_env_param(env)

    # 请求 LLM 评判结果（0-100）；≥PASS_SCORE 完成，否则重生成。
    def _verify(self, stdout: str) -> None:
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"目标/期望输出:\n{self.input.get_goal() or self.input.get_content() or ''}\n"
                    f"程序输出:\n{stdout}\n"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    "请根据目标/期望输出，评判上述程序输出是否符合目标/期望输出，"
                    "给出 0 到 100 的整数分值（100 为完全符合），并给出当前程序结论不达标的唯一准确原因。"
                    "只依据程序输出是否达成目标/期望输出打分，不评判代码风格。"
                ),
            },
        ]
        flow_out = self.generateFlowOutput(AERoleExcuterScriptFunction.receiveScriptVerify)
        flow_out.set_llm_out({
            "score": llm_generate("0到100的整数分值，100为完全符合预期"),
            "reason": llm_generate("当前程序结论不达标的唯一准确原因"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 验证脚本执行结果", self.title, self.deepth)
        self.flow_send_llm_request(payload)

    # 接收验证评分；≥PASS_SCORE 完成，否则带历次记录（含不达标理由）请求修正。
    def receiveScriptVerify(self, data: dict) -> bool:
        # 无当前 attempt 接收验证结果，属异常状态，直接以错误完成本 flow
        if not self.attempts:
            logger.warning("[%s][d=%s] 收到验证评分但无当前 attempt，以错误完成本 flow 避免卡死",
                           self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "验证评分回包无对应 attempt"},
                AEFlowCompletEvent.error,
            )
            return True
        # 由当前 attempt 自行解析打分数据（score + reason）并回填
        att = self.attempts[-1]
        att.apply_verify_result(data)
        score = att.score
        reason = att.reason
        verify_count = sum(1 for a in self.attempts if a.score is not None)
        pending_stdout = att.stdout
        if score >= self.PASS_SCORE:
            logger.info("[%s][d=%s] 脚本验证通过(score=%d≥%d)，记录执行结果:\n%s",
                        self.title, self.deepth, score, self.PASS_SCORE, pending_stdout)
            self._complete()
            return True
        logger.warning("[%s][d=%s] 脚本验证未通过(score=%d<%d, 不达标理由=%s)，带历次执行记录重新生成脚本重试[第%d次]",
                       self.title, self.deepth, score, self.PASS_SCORE, reason, verify_count)
        self._request_script_fix(
            "历次执行结果均未符合目标/期望输出，请对照目标、历次脚本/结果与不达标理由修正脚本。",
            include_history=True,
        )
        return True

    # 请求 LLM 修正脚本；include_history=True 带历次记录，否则仅带当前脚本与错误。
    def _request_script_fix(self, problem: str, include_history: bool = False) -> None:
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
        if include_history and self.attempts:
            # 每个 attempt 自行拼装消息块（含脚本/执行结果/不达标理由），供下次 LLM 正确认识到问题
            history_lines = [att.to_history_message(i) for i, att in enumerate(self.attempts)]
            assistant_content = (
                f"脚本类型: {self.type}\n"
                f"目标/期望输出:\n{self.input.get_goal() or self.input.get_content() or ''}\n"
                f"历次执行记录（脚本内容 + 执行结果 + 不达标理由）:\n"
                + "\n".join(history_lines) + "\n"
                f"问题说明:\n{problem}\n"
                "请依据目标/期望输出与历次执行结果修正脚本，使其执行后在 stdout 产出目标/期望输出。"
            )
        else:
            assistant_content = (
                f"脚本类型: {self.type}\n"
                f"目标/期望输出:\n{self.input.get_goal() or self.input.get_content() or ''}\n"
                f"当前脚本内容:\n{self.attempts[-1].script}\n"
                f"问题说明:\n{problem}\n"
                "请依据问题说明修正脚本，使其产出目标/期望输出。"
            )
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: assistant_content,
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: "请输出修正后的完整脚本内容（仅脚本代码本身，不要解释、不要 markdown 代码块标记）。",
            },
        ]
        flow_out = self.generateFlowOutput(AERoleExcuterScriptFunction.receiveScriptFix)
        flow_out.set_llm_out({"script": llm_generate("修正后的完整脚本内容")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 修正脚本%s",
                    self.title, self.deepth, "（含历次执行记录）" if include_history else "")
        self.flow_send_llm_request(payload)

    # 接收修正脚本，创建新 attempt 后重新执行。
    def receiveScriptFix(self, data: dict) -> bool:
        fixed = data.get("script") if isinstance(data, dict) else None
        if fixed is None and isinstance(data, str):
            fixed = data
        fixed = (fixed or "").strip()
        self.attempts.append(AEScriptAttempt(script=fixed))
        logger.info("[%s][d=%s] 收到修正脚本，重新执行", self.title, self.deepth)
        self._run_script()
        return True
