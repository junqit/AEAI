"""
AEScript - 脚本 Flow，继承 AEFlow。

脚本信息（title / script / type）通过 update 方法设置。
执行由 AEScriptRunner 完成；执行失败时自动请求 LLM 修正脚本并重试（最多 MAX_RETRIES 次）。
脚本执行成功后，先以「名称 + 脚本内容 + 执行结果」请求 LLM 评判是否符合预期（0-100 分），
≥PASS_SCORE 才完成；否则以「名称 + python 源码」重新请求 LLM 重生成脚本再执行再验证，
验证不达标无次数限制地重试直到通过；执行失败修正仍受 MAX_RETRIES 约束。
"""
import logging
import re
from enum import Enum

from WorkFlows.FlowWork.AEFlow import AEFlow
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput, AEFlowStatus
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_TITLE, AE_CONTENT
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AEScriptFunction(AEFunctional):
    """AEScript 专属回包功能性方法名。"""
    receiveScriptFix = "receiveScriptFix"
    receiveScriptVerify = "receiveScriptVerify"


class AEScriptType(str, Enum):
    """脚本类型常量枚举"""
    python = "python"
    shell = "shell"
    ruby = "ruby"


class AEScript(AEFlow):
    """脚本 Flow：title=作用，script=脚本内容，type=脚本类型。

    执行失败时自动请求 LLM 修正脚本并重试（最多 MAX_RETRIES 次）。
    执行成功后经 LLM 验证（0-100 分），≥PASS_SCORE 才完成；不达标则无次数限制地重生成脚本重试，直到通过。
    """

    VALID_TYPES = tuple(t.value for t in AEScriptType)
    MAX_RETRIES = 3  # 脚本执行失败修正的最大重试次数（验证不达标重生成无次数限制）
    # LLM 验证通过阈值（0-100），≥此分才视为执行符合预期
    PASS_SCORE = 80

    script: str = ""
    type: str = ""

    INIT_SCHEMA = {
        AE_TITLE: "作用（脚本用途说明）",
        "script": "脚本内容",
        "type": "脚本类型，取值 python / shell / ruby 之一",
    }

    def update(self, title: str, script: str, type) -> None:
        """更新脚本信息。"""
        self.title = title or ""
        self.script = script or ""
        type_value = type.value if isinstance(type, AEScriptType) else type
        if type_value not in self.VALID_TYPES:
            raise ValueError(f"AEScript.type 非法: {type!r}，应为 {self.VALID_TYPES} 之一")
        self.type = type_value

    def outResult_summary(self) -> str:
        """组装脚本作用与执行结果（stdout）为总结内容，供父 flow 汇总。

        AEScript 非角色 flow（不经问题优化），故以 title（脚本用途）作为上下文。
        验证通过时附带 LLM 验证分数，便于汇总时知晓该结果已经过校验。
        """
        answer = self.outResult.get(AE_CONTENT, "") if isinstance(self.outResult, dict) else ""
        base = f"{self.title} 我的回答：{answer}" if self.title else f"我的回答：{answer}"
        if self._verified_score is not None:
            base += f"（LLM 验证通过 score={self._verified_score}/100）"
        return base

    def on_flow_start(self, flowInput) -> bool:
        """启动：直接执行脚本。"""

        self.status = AEFlowStatus.processing
        self._retry_count = 0
        self._last_error = ""
        self._pending_stdout = ""
        self._verify_count = 0
        self._verified_score = None
        self._verified_reason = ""
        self._run_script()
        return True

    def _run_script(self) -> None:
        """执行脚本；成功则交 LLM 验证，失败且有重试次数则请求 LLM 修正，否则以空结果完成。"""
        from .AEScriptRunner import get_runner
        try:
            runner = get_runner(self.type)
            stdout = runner.run(self.script)
            # 成功：交 LLM 验证是否符合预期（≥PASS_SCORE 才完成）
            logger.info("[%s][d=%s] 脚本执行成功(type=%s)", self.title, self.deepth, self.type)
            self._verify(stdout)
        except Exception as e:
            self._last_error = str(e)  # 完整错误（含 stdout/stderr）供 LLM 修正脚本使用
            logger.error("[%s][d=%s] 脚本执行失败(type=%s, retry=%d/%d)",
                         self.title, self.deepth, self.type, self._retry_count, self.MAX_RETRIES)
            if self._retry_count < self.MAX_RETRIES:
                self._retry_count += 1
                self._request_script_fix(self._last_error)
            else:
                logger.warning("[%s][d=%s] 重试次数用完(%d)，以空结果完成", self.title, self.deepth, self.MAX_RETRIES)
                self._complete("")

    def _complete(self, stdout: str) -> None:
        """以执行结果完成本 flow，回传父 flow。"""
        if not isinstance(stdout, str):
            stdout = str(stdout or "")
        delegate_ident = self.delegate.ident if self.delegate is not None else self.ident
        self.flow_receive_complete({AE_IDENT: delegate_ident, AE_CONTENT: stdout})

    def _apply_script_env(self, payload) -> None:
        """脚本相关 LLM 请求只携带 python/ruby 版本与库信息，去掉默认的 system（OS/硬件/系统工具）环境。"""
        from Context.Context.AELLMPayload import AEEnvParamType
        payload.remove_env_param(AEEnvParamType.system)
        payload.add_env_param(AEEnvParamType.python)
        payload.add_env_param(AEEnvParamType.ruby)

    def _verify(self, stdout: str) -> None:
        """执行成功后请求 LLM 评判结果是否符合预期（0-100）。

        以脚本名称(title) + 脚本内容 + 执行结果(stdout) 请求 LLM 打分。
        ≥PASS_SCORE 才完成；<PASS_SCORE 由 receiveScriptVerify 触发重生成。
        """
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE
        self._pending_stdout = stdout
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"脚本名称: {self.title}\n"
                    f"脚本类型: {self.type}\n"
                    f"脚本内容:\n{self.script}\n"
                    f"执行结果(stdout):\n{stdout}\n"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    "请根据脚本名称所表达的用途与脚本内容，评判上述执行结果是否符合预期，"
                    "给出 0 到 100 的整数分值（100 为完全符合预期），并给出简短评分理由。"
                    "只依据执行结果是否达成脚本用途打分，不评判代码风格。"
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
        """接收 LLM 验证评分：≥PASS_SCORE 完成本 flow；否则无次数限制地重生成脚本重试，直到通过。"""
        score = self._parse_score(data.get("score")) if isinstance(data, dict) else 0
        reason = data.get("reason", "") if isinstance(data, dict) else ""
        self._verify_count += 1
        logger.info("[%s][d=%s] 收到 LLM 验证评分: score=%d/100 (通过阈值 %d), reason=%s [第%d次验证]",
                    self.title, self.deepth, score, self.PASS_SCORE, reason, self._verify_count)
        if score >= self.PASS_SCORE:
            self._verified_score = score
            self._verified_reason = reason
            logger.info("[%s][d=%s] 脚本验证通过(score=%d≥%d)，记录执行结果:\n%s",
                        self.title, self.deepth, score, self.PASS_SCORE, self._pending_stdout)
            self._complete(self._pending_stdout)
            return True
        logger.warning("[%s][d=%s] 脚本验证未通过(score=%d<%d)，无次数限制，重新生成脚本重试[第%d次]",
                       self.title, self.deepth, score, self.PASS_SCORE, self._verify_count)
        self._request_script_fix(
            f"脚本执行成功但结果不符合预期（符合度评分 {score}/{self.PASS_SCORE}，低于阈值）。"
            f"评分理由：{reason}。请根据脚本名称与源码重新生成脚本，使执行结果更符合脚本用途预期。"
        )
        return True

    @staticmethod
    def _parse_score(value) -> int:
        """容错解析 0-100 整数分值：int/float 取整；str 取首个整数；越界夹到 [0,100]；解析失败返回 0。"""
        if isinstance(value, bool):  # bool 是 int 子类，先排除
            return 0
        if isinstance(value, (int, float)):
            n = int(value)
        elif isinstance(value, str):
            m = re.search(r"\d+", value)
            n = int(m.group()) if m else 0
        else:
            n = 0
        return max(0, min(100, n))

    def _request_script_fix(self, problem: str) -> None:
        """请求 LLM 根据问题说明、脚本能力与内容修正脚本。

        problem 同时覆盖两种触发：脚本执行失败（含完整错误）与验证评分不达标（含分数与理由）。
        """
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"脚本类型: {self.type}\n"
                    f"脚本作用: {self.title}\n"
                    f"当前脚本内容:\n{self.script}\n"
                    f"问题说明:\n{problem}\n"
                    "请根据问题说明修正脚本中的问题。"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    "请输出修正后的完整脚本内容（仅脚本代码本身，不要解释、不要 markdown 代码块标记）。"
                    "修正后的脚本必须真正解决上述问题说明指出的问题——不得回避、不得用占位符、"
                    "伪代码或注释绕过、不得输出与原脚本实质等价或仅作无关微调的代码，"
                    "必须给出能实际运行并产出符合预期结果的修正实现。"
                    "脚本在只读沙箱中执行，禁止任何文件写入（创建/修改/删除/重命名、open(... 'w'/'a')、"
                    "> / >> 重定向等），需输出结果一律用 stdout；若原问题由写文件引起，须改为不写文件。"
                ),
            },
        ]
        flow_out = self.generateFlowOutput(AEScriptFunction.receiveScriptFix)
        flow_out.set_llm_out({"script": llm_generate("修正后的完整脚本内容")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self._apply_script_env(payload)
        logger.info("[%s][d=%s] 请求 LLM 修正脚本", self.title, self.deepth)
        self.send_llm_payload(payload)

    def receiveScriptFix(self, data: dict) -> bool:
        """接收 LLM 修正后的脚本，更新 self.script 并重新执行。"""
        fixed = data.get("script") if isinstance(data, dict) else None
        if fixed is None and isinstance(data, str):
            fixed = data
        self.script = (fixed or "").strip()
        logger.info("[%s][d=%s] 收到修正脚本(retry=%d)，重新执行", self.title, self.deepth, self._retry_count)
        self._run_script()
        return True
