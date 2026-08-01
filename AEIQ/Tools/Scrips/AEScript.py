"""
AEScript - 脚本 Flow，继承 AEFlow。

脚本信息（title / script / type）通过 update 方法设置。
执行由 AEScriptRunner 完成；执行失败时自动请求 LLM 修正脚本并重试（最多 MAX_RETRIES 次）。
"""
import logging
from enum import Enum

from WorkFlows.FlowWork.AEFlow import AEFlow
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_TITLE, AE_ANSWER

logger = logging.getLogger(__name__)


class AEScriptType(str, Enum):
    """脚本类型常量枚举"""
    python = "python"
    shell = "shell"
    ruby = "ruby"


class AEScript(AEFlow):
    """脚本 Flow：title=作用，script=脚本内容，type=脚本类型。

    执行失败时自动请求 LLM 修正脚本并重试（最多 MAX_RETRIES 次）。
    """

    VALID_TYPES = tuple(t.value for t in AEScriptType)
    MAX_RETRIES = 3  # 脚本执行失败后的最大重试次数
    # stdout 最大长度（超出截断），防止大输出（如读取大文件）经 outResult_summary 撑爆上层 summarize 的 LLM 请求体
    MAX_STDOUT_LEN = 20000

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
        """
        answer = self.outResult.get(AE_ANSWER, "") if isinstance(self.outResult, dict) else ""
        if self.title:
            return f"{self.title} 我的回答：{answer}"
        return f"我的回答：{answer}"

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：执行脚本；失败则请求 LLM 修正后重试。"""
        if not super().startFlow(AEFlowInput(content="")):
            return
        self._retry_count = 0
        self._last_error = ""
        self._run_script()

    def _run_script(self) -> None:
        """执行脚本；成功则完成，失败且有重试次数则请求 LLM 修正，否则以空结果完成。"""
        from .AEScriptRunner import get_runner
        try:
            runner = get_runner(self.type)
            stdout = runner.run(self.script)
            # 成功
            logger.info("[%s][d=%s] 脚本执行成功(type=%s)", self.title, self.deepth, self.type)
            self._complete(stdout)
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
        """以执行结果完成本 flow，回传父 flow。stdout 过长则截断，防止撑爆上层 summarize 的 LLM 请求体。"""
        if isinstance(stdout, str) and len(stdout) > self.MAX_STDOUT_LEN:
            stdout = stdout[:self.MAX_STDOUT_LEN] + f"\n...（已截断，原始长度 {len(stdout)} 字符）"
        delegate_ident = self.delegate.ident if self.delegate is not None else self.ident
        self.flow_receive_complete({AE_IDENT: delegate_ident, AE_ANSWER: stdout})

    def _request_script_fix(self, error: str) -> None:
        """请求 LLM 根据错误信息、脚本能力与内容修正脚本。"""
        from Context.Context.AELLMPayload import AELLMPayload, llm_generate
        from Roles.AERoleType import AEConentRole, AE_ROLE, AE_CONTENT
        messages = [
            {
                AE_ROLE: AEConentRole.ASSISTANT.value,
                AE_CONTENT: (
                    f"脚本类型: {self.type}\n"
                    f"脚本作用: {self.title}\n"
                    f"出错脚本内容:\n{self.script}\n"
                    f"错误信息:\n{error}\n"
                    "请根据错误信息修正脚本中的问题。"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: (
                    "请输出修正后的完整脚本内容（仅脚本代码本身，不要解释、不要 markdown 代码块标记）。"
                    "修正须解决上述错误信息指出的问题。"
                    "脚本在只读沙箱中执行，禁止任何文件写入（创建/修改/删除/重命名、open(... 'w'/'a')、"
                    "> / >> 重定向等），需输出结果一律用 stdout；若原错误由写文件引起，须改为不写文件。"
                ),
            },
        ]
        flow_out = self.generateFlowOutput("receiveScriptFix")
        flow_out.set_llm_out({"script": llm_generate("修正后的完整脚本内容")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        logger.info("[%s][d=%s] 请求 LLM 修正脚本(retry=%d/%d)", self.title, self.deepth, self._retry_count, self.MAX_RETRIES)
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
