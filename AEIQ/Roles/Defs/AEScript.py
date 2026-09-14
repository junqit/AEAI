"""
AEScript - 脚本 Flow，继承 AERoleExcutor（拥有角色执行的同等能力）。本类覆写 on_flow_start
跳过角色信息/优化/选择链路——脚本是叶子执行单元，无下层角色可选。

流程：start_flow → LLM 按当前 ruby/python/shell 能力与已装工具包选脚本类型 → LLM 生成脚本内容
→ 执行 → LLM 验证评分。目标（expected_output）由上层经公共接口 receive_flow_input 写入 self.input.goal；
脚本必须经 LLM 验证评分 ≥PASS_SCORE 才完成。执行失败或验证不达标均请求 LLM 修正/重生成脚本后
重试，直到验证通过；设双重保护——重试达 MAX_RETRIES 次或连续 SAME_ERROR_LIMIT 次相同错误，
判定 LLM 修不动，以失败摘要反馈完成，不以空结果结束。
"""
import logging
import re
from enum import Enum

from Roles.Defs.AERoleExcutor import AERoleExcutor
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


class AEScript(AERoleExcutor):
    """脚本 Flow：目标（expected_output）= self.input.goal（上层经公共接口 receive_flow_input 注入）；
    type/script 由本 flow 经 LLM 选型 + 生成后执行。

    流程：on_flow_start（置 self.input）→ start_flow → _request_script_type（LLM 选型）→
    receiveScriptType → _request_script_generate（LLM 生成内容）→ receiveScriptGenerate →
    _run_script → _verify（≥PASS_SCORE 完成；不达标 _request_script_fix 重试）。执行失败亦经
    _request_script_fix 重试。双重保护：重试达 MAX_RETRIES 或连续 SAME_ERROR_LIMIT 次相同错误，
    判定 LLM 修不动，以失败摘要反馈完成，不以空结果结束。
    """

    VALID_TYPES = tuple(t.value for t in AEScriptType)
    MAX_RETRIES = 100
    SAME_ERROR_LIMIT = 5
    PASS_SCORE = 80

    script: str = ""        # 脚本代码（由本 flow 选型+生成）
    type: str = ""

    def outResult_summary(self) -> str:
        """组装执行结果（stdout）为总结内容，供父 flow 汇总。验证通过时附带分数。"""
        answer = self.output.outResult or ""
        base = f"我的回答：{answer}"
        if self._verified_score is not None:
            base += f"（LLM 验证通过 score={self._verified_score}/100）"
        return base

    def on_flow_start(self, flowInput) -> bool:
        """启动：置 self.input（公共接口）+ 计数器，交 start_flow（选型→生成→执行）。"""
        self.input = flowInput
        self.status = AEFlowStatus.processing
        self._retry_count = 0
        self._last_error = ""
        self._prev_error = ""
        self._same_error_count = 0
        self._pending_stdout = ""
        self._verify_count = 0
        self._verified_score = None
        self._verified_reason = ""
        self.start_flow()
        return True

    def start_flow(self) -> None:
        """流程入口：LLM 按当前 ruby/python/shell 能力与已装工具包选脚本类型，选定后再
        LLM 生成脚本内容并执行（错误/不达标自动重试）。"""
        self._request_script_type()

    def _goal(self) -> str:
        """目标/期望输出（由上层经 receive_flow_input 写入 self.input.goal）。"""
        return (self.input.goal if self.input is not None else "") or ""

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
                    "- 必须切实产出目标/期望输出，不得拒绝、推诿或用占位符/伪代码绕过\n"
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
        """接收 LLM 生成的脚本内容（type 已由 receiveScriptType 选定），置 self.script 后执行。"""
        script = data.get("script") if isinstance(data, dict) else None
        if script is None and isinstance(data, str):
            script = data
        self.script = (script or "").strip()
        if not self.script:
            logger.warning("[%s][d=%s] 生成脚本为空，以错误完成", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "脚本生成失败：LLM 未返回脚本代码"},
                AEFlowCompletEvent.error,
            )
            return True
        self._run_script()
        return True

    def _run_script(self) -> None:
        """执行脚本；成功则交 LLM 验证（必须 ≥PASS_SCORE 才完成），失败则请求 LLM 修正后重试。

        双重保护：重试达 MAX_RETRIES 或连续 SAME_ERROR_LIMIT 次相同错误，判定 LLM 修不动，
        以失败摘要（重试次数+最后错误）反馈完成，不以空结果结束。
        """
        from Tools.Scrips.AEScriptRunner import get_runner
        try:
            runner = get_runner(self.type)
            stdout = runner.run(self.script)
            logger.info("[%s][d=%s] 脚本执行成功(type=%s)", self.title, self.deepth, self.type)
            self._verify(stdout)
        except Exception as e:
            self._last_error = str(e)
            self._retry_count += 1
            if self._last_error == self._prev_error:
                self._same_error_count += 1
            else:
                self._same_error_count = 1
                self._prev_error = self._last_error
            if self._retry_count >= self.MAX_RETRIES or self._same_error_count >= self.SAME_ERROR_LIMIT:
                failure_summary = (
                    f"脚本执行失败：重试 {self._retry_count}/{self.MAX_RETRIES} 次，"
                    f"连续相同错误 {self._same_error_count}/{self.SAME_ERROR_LIMIT} 次，"
                    f"LLM 未能修正脚本。最后错误：{self._last_error}"
                )
                logger.warning("[%s][d=%s] %s，以失败摘要反馈完成", self.title, self.deepth, failure_summary)
                self._complete(failure_summary)
                return
            logger.error("[%s][d=%s] 脚本执行失败(type=%s, retry=%d/%d, 连续相同错误=%d/%d)，请求 LLM 修正后重试",
                         self.title, self.deepth, self.type, self._retry_count, self.MAX_RETRIES,
                         self._same_error_count, self.SAME_ERROR_LIMIT)
            self._request_script_fix(self._last_error)

    def _complete(self, stdout: str) -> None:
        """以执行结果完成本 flow，回传父 flow。"""
        if not isinstance(stdout, str):
            stdout = str(stdout or "")
        delegate_ident = self.delegate.ident if self.delegate is not None else self.ident
        self.flow_receive_complete({AE_IDENT: delegate_ident, AE_CONTENT: stdout})

    def _apply_script_env(self, payload) -> None:
        """脚本相关 LLM 请求携带 python/ruby/shell 能力与已装工具包信息（去掉默认 system 环境）。"""
        from Context.Context.AELLMPayload import AEEnvParamType
        payload.remove_env_param(AEEnvParamType.system)
        payload.add_env_param(AEEnvParamType.python)
        payload.add_env_param(AEEnvParamType.ruby)
        payload.add_env_param(AEEnvParamType.shell)

    def _verify(self, stdout: str) -> None:
        """执行成功后请求 LLM 评判结果是否符合目标/期望输出（0-100）。

        ≥PASS_SCORE 才完成；<PASS_SCORE 由 receiveScriptVerify 触发重生成。
        """
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE
        self._pending_stdout = stdout
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"目标/期望输出:\n{self._goal()}\n"
                    f"脚本内容:\n{self.script}\n"
                    f"执行结果(stdout):\n{stdout}\n"
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
            f"评分理由：{reason}。请重新生成脚本，使执行结果更符合目标/期望输出。"
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
                    f"目标/期望输出:\n{self._goal()}\n"
                    f"当前脚本内容:\n{self.script}\n"
                    f"问题说明:\n{problem}\n"
                    "请根据问题说明修正脚本，使其产出目标/期望输出。"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    "请输出修正后的完整脚本内容（仅脚本代码本身，不要解释、不要 markdown 代码块标记）。"
                    "修正后的脚本必须真正解决上述问题说明指出的问题——不得回避、不得用占位符、"
                    "伪代码或注释绕过、不得输出与原脚本实质等价或仅作无关微调的代码，"
                    "必须给出能实际运行并产出目标/期望输出的修正实现。"
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
