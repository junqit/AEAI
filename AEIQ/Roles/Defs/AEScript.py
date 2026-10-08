"""
AEScript - 脚本 Flow，继承 AERoleExcutor（拥有角色执行的同等能力）。本类覆写 on_flow_start
跳过角色信息/优化/选择链路——脚本是叶子执行单元，无下层角色可选。

流程：start_flow → LLM 按当前 ruby/python/shell 能力与已装工具包选脚本类型 → LLM 生成脚本内容
→ 执行 → LLM 验证评分。目标（expected_output）由上层经公共接口 receive_flow_input 写入 self.input.goal；
脚本必须经 LLM 验证评分 ≥PASS_SCORE 才完成。执行失败或验证不达标均请求 LLM 修正/重生成脚本后
重试，循环直至验证通过。
执行记账（历次执行/验证记录）由 AEScript 实例直接持有（self.attempts），
不污染入站 input / 出站 output 契约；outResult 由历次 attempt 组装（每次执行结果，不论 verify 是否通过）。
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from Roles.Defs.AERoleExcutor import AERoleExcutor
from Roles.AERoleType import AEFlowRole
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from WorkFlows.FlowWork.AEFlowInput import AEFlowStatus
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AEScriptFunction(AEFunctional):
    """AEScript 专属回包功能性方法名。"""
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
    回填到同一实例；AEScript 不另存脚本内容，当前 attempt = self.attempts[-1]。
    last_error/pending_stdout/verified_score/verify_count 等均由历次 attempt 派生，不另存冗余字段。
    """
    script: str = ""
    stdout: str = ""
    error: str = ""
    score: Optional[int] = None
    reason: str = ""


class AEScript(AERoleExcutor):
    """脚本 Flow：目标（expected_output）= self.input.goal（上层经公共接口 receive_flow_input 注入）；
    type 由本 flow 经 LLM 选型后贯穿执行；脚本内容由 LLM 生成并存于每次 attempt
    （AEScriptAttempt.script），不在实例上冗余留存，当前 attempt = self.attempts[-1]。

    流程：on_flow_start（置 self.input + 执行记账）→ start_flow → _request_script_type（LLM 选型）→
    receiveScriptType → _request_script_generate（LLM 生成内容）→ receiveScriptGenerate →
    _run_script（执行结果回填到当前 attempt）→ _verify（≥PASS_SCORE 完成；不达标 _request_script_fix 重试）。
    执行失败亦经 _request_script_fix 重试。循环直至验证通过。outResult 由历次 attempt 组装（每次结果，不论对错）。

    实例执行记账：self.attempts（历次 AEScriptAttempt，含脚本/结果/评分）为信息源。
    """

    @classmethod
    def _role(cls):
        return AEFlowRole.script

    VALID_TYPES = tuple(t.value for t in AEScriptType)
    PASS_SCORE = 80

    type: str = ""

    def outResult_summary(self) -> str:
        """组装执行结果为总结内容，供父 flow 汇总。列出每次结果（不论对错）+ 验证分。"""
        results = self.output.outResult
        if not results:
            return "我的回答：（无结果）"
        if isinstance(results, list):
            body = "\n".join(f"第{i+1}次：{r}" for i, r in enumerate(results))
        else:
            body = str(results)
        base = f"我的回答：\n{body}"
        score = self.attempts[-1].score if self.attempts else None
        if score is not None:
            base += f"\n（LLM 验证通过 score={score}/100）"
        return base

    def on_flow_start(self, flowInput) -> bool:
        """启动：置 self.input（入站契约）+ 执行记账（历次执行），交 start_flow（选型→生成→执行→验证循环）。"""
        self.input = flowInput
        self.status = AEFlowStatus.processing
        self.attempts = []
        self.start_flow()
        return True

    def start_flow(self) -> None:
        """流程入口：LLM 按当前 ruby/python/shell 能力与已装工具包选脚本类型，选定后再
        LLM 生成脚本内容并执行（错误/不达标自动重试，循环至通过）。"""
        self._request_script_type()

    def _goal(self) -> str:
        """目标/期望输出：优先 self.input.goal；经 _create_role_flows 直接派发时仅有 content，回退取 content。"""
        if self.input is None:
            return ""
        return self.input.goal or self.input.parameter.get(AE_CONTENT, "") or ""

    def _request_script_type(self) -> None:
        """请求 LLM 按当前 ruby/python/shell 能力与已安装工具包，选择最适合实现目标的脚本类型。"""
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: f"目标/期望输出:\n{self._goal()}\n",
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
        flow_out = self.generateFlowOutput(AEScriptFunction.receiveScriptType)
        flow_out.set_llm_out({
            "type": llm_generate("脚本类型：python / shell / ruby 之一，按当前能力与已装工具包选最适合的"),
            "reason": llm_generate("简短理由：为何该类型最适合"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 选择脚本类型", self.title, self.deepth)
        self.send_llm_payload(payload)

    def receiveScriptType(self, data: dict) -> bool:
        """接收 LLM 选择的脚本类型，置 self.type 后请求生成脚本内容。"""
        type_value = data.get("type") if isinstance(data, dict) else ""
        type_value = type_value.value if isinstance(type_value, AEScriptType) else type_value
        if type_value not in self.VALID_TYPES:
            logger.warning("[%s][d=%s] 选型 type=%r 非法，默认 python", self.title, self.deepth, type_value)
            type_value = "python"
        self.type = type_value
        logger.info("[%s][d=%s] 选定脚本类型: %s", self.title, self.deepth, self.type)
        self._request_script_generate()
        return True

    def _request_script_generate(self) -> None:
        """类型已选定，请求 LLM 生成该类型脚本内容以产出目标/期望输出。"""
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"目标/期望输出:\n{self._goal()}\n"
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
                    "- 必须切实解决上述目标/期望输出所指的用户目标与问题，不得拒绝、推诿或用占位符/伪代码绕过\n"
                    "- 不得瞎写：禁止捏造数据或结果，所需数据须真实获取或计算得出，不得用伪造值冒充目标/期望输出\n"
                    "- 可无人值守执行，禁止交互输入（input/gets/read），参数硬编码或用环境变量\n"
                    "- 只读沙箱执行，禁止写文件（创建/修改/删除、open 写模式、> / >> 重定向等），中间结果用 stdout 输出\n"
                    "- 联网获取数据优先用爬虫，使用国内可访问的地址，避免境外 API"
                ),
            },
        ]
        flow_out = self.generateFlowOutput(AEScriptFunction.receiveScriptGenerate)
        flow_out.set_llm_out({"script": llm_generate("可执行的脚本文本")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 生成 %s 脚本内容", self.title, self.deepth, self.type)
        self.send_llm_payload(payload)

    def receiveScriptGenerate(self, data: dict) -> bool:
        """接收 LLM 生成的脚本内容（type 已由 receiveScriptType 选定），创建 attempt 后执行。

        每次收到新脚本即创建 AEScriptAttempt（脚本内容唯一存 attempt），执行结果/验证评分均回填到
        该 attempt；AEScript 不持有脚本内容，当前 attempt = self.attempts[-1]。空脚本以错误完成。"""
        script = data.get("script") if isinstance(data, dict) else None
        if script is None and isinstance(data, str):
            script = data
        script = (script or "").strip()
        if not script:
            logger.warning("[%s][d=%s] 生成脚本为空，以错误完成", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: ["脚本生成失败：LLM 未返回脚本代码"]},
                AEFlowCompletEvent.error,
            )
            return True
        self.attempts.append(AEScriptAttempt(script=script))
        self._run_script()
        return True

    def _run_script(self) -> None:
        """执行当前 attempt（self.attempts[-1]）的脚本；成功回填 stdout 并交 LLM 验证，
        失败回填 error 并请求 LLM 修正后重试（不限次数）。

        attempt 在收到脚本时已创建（receiveScriptGenerate/receiveScriptFix），此处只回填执行结果；
        验证评分由 receiveScriptVerify 回填到同一 attempt。循环直至验证通过。
        """
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

    def _build_results(self) -> List[str]:
        """由历次 attempt 组装出站结果：每次执行结果（成功记 stdout，失败记 [失败] 错误），不论对错。"""
        out = []
        for att in self.attempts:
            out.append(f"[失败] {att.error}" if att.error else att.stdout)
        return out

    def _complete(self) -> None:
        """以执行结果完成本 flow，回传父 flow。outResult 由历次 attempt 组装（每次结果，不论对错）。"""
        delegate_ident = self.delegate.ident if self.delegate is not None else self.ident
        self.flow_receive_complete({AE_IDENT: delegate_ident, AE_CONTENT: self._build_results()})

    def _apply_script_env(self, payload) -> None:
        """脚本相关 LLM 请求携带脚本能力与已装工具包信息（去掉默认 system 环境）。

        选型前（self.type 未定）携带 python/ruby/shell 全部能力，供 LLM 比较后选型；
        选型后（self.type 已定）仅携带选定类型对应能力，聚焦上下文、减少无关噪声。
        """
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

    def _verify(self, stdout: str) -> None:
        """执行成功后请求 LLM 评判结果是否符合目标/期望输出（0-100）。

        ≥PASS_SCORE 才完成；<PASS_SCORE 由 receiveScriptVerify 触发重生成。
        """
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"目标/期望输出:\n{self._goal()}\n"
                    f"脚本内容:\n{self.attempts[-1].script}\n"
                    f"程序输出:\n{stdout}\n"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    "请根据目标/期望输出与脚本内容，评判上述执行结果是否符合目标/期望输出，"
                    "给出 0 到 100 的整数分值（100 为完全符合），并给出简短评分理由。"
                    "只依据执行结果是否达成目标/期望输出打分，不评判代码风格。"
                ),
            },
        ]
        flow_out = self.generateFlowOutput(AEScriptFunction.receiveScriptVerify)
        flow_out.set_llm_out({
            "score": llm_generate("0到100的整数分值，100为完全符合预期"),
            "reason": llm_generate("简短评分理由"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 验证脚本执行结果", self.title, self.deepth)
        self.send_llm_payload(payload)

    def receiveScriptVerify(self, data: dict) -> bool:
        """接收 LLM 验证评分：≥PASS_SCORE 完成本 flow；否则带历次执行记录请求 LLM 修正（不含评分）。

        评分与理由回填到最近一次 attempt（记账留存），但不随修正请求交给 LLM——修正请求只带
        历次脚本内容与执行结果，供 LLM 对照目标定位差距。verify_count / pending_stdout 等
        均由历次 attempt 派生，不另存字段。
        """
        score = self._parse_score(data.get("score")) if isinstance(data, dict) else 0
        reason = data.get("reason", "") if isinstance(data, dict) else ""
        if self.attempts:
            self.attempts[-1].score = score
            self.attempts[-1].reason = reason
        verify_count = sum(1 for a in self.attempts if a.score is not None)
        pending_stdout = self.attempts[-1].stdout if self.attempts else ""
        logger.info("[%s][d=%s] 收到 LLM 验证评分: score=%d/100 (通过阈值 %d), reason=%s [第%d次验证]",
                    self.title, self.deepth, score, self.PASS_SCORE, reason, verify_count)
        if score >= self.PASS_SCORE:
            logger.info("[%s][d=%s] 脚本验证通过(score=%d≥%d)，记录执行结果:\n%s",
                        self.title, self.deepth, score, self.PASS_SCORE, pending_stdout)
            self._complete()
            return True
        logger.warning("[%s][d=%s] 脚本验证未通过(score=%d<%d)，带历次执行记录重新生成脚本重试[第%d次]",
                       self.title, self.deepth, score, self.PASS_SCORE, verify_count)
        self._request_script_fix(
            "历次执行结果均未符合目标/期望输出，请对照目标与历次脚本/结果修正脚本。",
            include_history=True,
        )
        return True

    @staticmethod
    def _parse_score(value) -> int:
        """容错解析 0-100 整数分值：int/float 取整；str 取首个整数；越界夹到 [0,100]；解析失败返回 0。"""
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

    def _request_script_fix(self, problem: str, include_history: bool = False) -> None:
        """请求 LLM 修正脚本，使其产出目标/期望输出。

        include_history=True（验证不达标触发）：把历次执行的脚本内容与执行结果（不含评分）
        全部交给 LLM，供其对照目标定位差距后修正；problem 不含分数/理由。
        include_history=False（执行失败触发）：仅给当前脚本与错误（problem）。
        """
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE
        if include_history and self.attempts:
            history_lines = []
            for i, att in enumerate(self.attempts):
                history_lines.append(f"—— 第 {i + 1} 次 ——")
                history_lines.append(f"脚本内容:\n{att.script}")
                if att.error:
                    history_lines.append(f"执行结果: 执行失败 → {att.error}")
                else:
                    history_lines.append(f"程序输出:\n{att.stdout}")
            assistant_content = (
                f"脚本类型: {self.type}\n"
                f"目标/期望输出:\n{self._goal()}\n"
                f"历次执行记录（脚本内容 + 执行结果，不含评分）:\n"
                + "\n".join(history_lines) + "\n"
                f"问题说明:\n{problem}\n"
                "请依据目标/期望输出与历次执行结果修正脚本，使其执行后在 stdout 产出目标/期望输出。"
            )
        else:
            assistant_content = (
                f"脚本类型: {self.type}\n"
                f"目标/期望输出:\n{self._goal()}\n"
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
                AE_CONTENT: (
                    "请输出修正后的完整脚本内容（仅脚本代码本身，不要解释、不要 markdown 代码块标记）。"
                    "修正后的脚本必须同时解决上述目标/期望输出与问题说明——不得回避问题，"
                    "不得用占位符、伪代码或注释绕过，不得输出与原脚本实质等价或仅作无关微调的代码。"
                    "修正后的脚本必须能正确执行，且执行后在 stdout 产出目标/期望输出——"
                    "产出内容必须能通过执行脚本实际获取到，不得依赖文件。"
                    "脚本在只读沙箱中执行，禁止任何文件写入（创建/修改/删除/重命名、open(... 'w'/'a')、"
                    "> / >> 重定向等），需输出结果一律用 stdout；若原问题由写文件引起，须改为不写文件。"
                ),
            },
        ]
        flow_out = self.generateFlowOutput(AEScriptFunction.receiveScriptFix)
        flow_out.set_llm_out({"script": llm_generate("修正后的完整脚本内容")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 修正脚本%s",
                    self.title, self.deepth, "（含历次执行记录）" if include_history else "")
        self.send_llm_payload(payload)

    def receiveScriptFix(self, data: dict) -> bool:
        """接收 LLM 修正后的脚本，创建新 attempt 并重新执行。

        修正脚本视为新脚本，创建新 AEScriptAttempt（脚本内容存 attempt），交 _run_script 回填执行结果。"""
        fixed = data.get("script") if isinstance(data, dict) else None
        if fixed is None and isinstance(data, str):
            fixed = data
        fixed = (fixed or "").strip()
        self.attempts.append(AEScriptAttempt(script=fixed))
        logger.info("[%s][d=%s] 收到修正脚本，重新执行", self.title, self.deepth)
        self._run_script()
        return True
