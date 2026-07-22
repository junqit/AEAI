"""
AEScriptRunner - 脚本执行器：python / shell / ruby 三种。

每种执行器以对应解释器运行脚本内容（AEScript.script），返回 stdout。
执行器本身不持有脚本，仅负责执行；由外部按 AEScript.type 选用。

权限：在 macOS(Darwin) 下用 sandbox-exec 包裹脚本，强制"全只读"——禁止任何文件写入
（含创建/修改/删除/重命名），允许读、网络与进程执行；非 macOS 暂无原生只读沙箱，
仅依赖 prompt 级只读约束（会打印警告）。
"""
import logging
import platform
import subprocess
from typing import Dict, Type, Optional

from .AEScript import AEScript, AEScriptType

logger = logging.getLogger(__name__)

# macOS sandbox-exec 全只读 profile：默认允许一切，仅拒绝所有文件写入类操作
# （file-write* 覆盖 file-write / file-write-data / file-write-unlink / file-write-rename 等）
_READ_ONLY_SANDBOX_PROFILE = "(version 1)\n(allow default)\n(deny file-write*)\n"

# 平台/沙箱不可用告警只打印一次，避免每次执行刷屏
_sandbox_unavailable_warned = False


class AEScriptRunner:
    """脚本执行器基类：以 [interpreter, flag, script_content] 方式运行脚本。"""

    # 子类覆写：解释器命令与脚本传入 flag
    interpreter: str = ""
    flag: str = ""

    def _build_command(self, script_content: str) -> list:
        """构建执行命令；macOS 下用 sandbox-exec 包裹强制全只读，否则原样执行。"""
        cmd = [self.interpreter, self.flag, script_content]
        if platform.system() == "Darwin":
            return ["sandbox-exec", "-p", _READ_ONLY_SANDBOX_PROFILE, *cmd]
        global _sandbox_unavailable_warned
        if not _sandbox_unavailable_warned:
            logger.warning(
                "[AEScriptRunner] 当前平台 %s 无原生只读沙箱，脚本以继承的 OS 权限执行"
                "（仅 prompt 级只读约束，未强制）",
                platform.system(),
            )
            _sandbox_unavailable_warned = True
        return cmd

    def run(self, script_content: str, timeout: Optional[float] = 30) -> str:
        """执行脚本内容，返回 stdout。

        Args:
            script_content: 脚本文本。
            timeout: 超时秒数；默认 30 秒，None 表示不限制。

        Returns:
            脚本 stdout。

        Raises:
            RuntimeError: 脚本退出码非 0 或解释器未配置。
        """
        if not self.interpreter or not self.flag:
            raise RuntimeError(f"{type(self).__name__} 未配置 interpreter/flag")
        command = self._build_command(script_content)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            # sandbox-exec 不存在等：回退到无沙箱执行并告警（只读未强制）
            global _sandbox_unavailable_warned
            if not _sandbox_unavailable_warned:
                logger.warning(
                    "[AEScriptRunner] sandbox-exec 不可用，回退到无沙箱执行（只读未强制）"
                )
                _sandbox_unavailable_warned = True
            result = subprocess.run(
                [self.interpreter, self.flag, script_content],
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"{self.interpreter} 执行失败(returncode={result.returncode})\n"
                f"  stdout: {result.stdout.strip()}\n"
                f"  stderr: {result.stderr.strip()}"
            )
        # 确保 stdout 为字符串
        stdout = result.stdout if isinstance(result.stdout, str) else str(result.stdout or "")
        print(f"[{self.interpreter}] 脚本执行结果:\n{stdout}")
        return stdout

    def run_script(self, script: AEScript, timeout: Optional[float] = None) -> str:
        """按 AEScript 执行其脚本内容。"""
        return self.run(script.script, timeout=timeout)


class AEPythonRunner(AEScriptRunner):
    """Python 脚本执行器：python3 -c <script>"""

    interpreter = "python"
    flag = "-c"


class AEShellRunner(AEScriptRunner):
    """Shell 脚本执行器：sh -c <script>"""

    interpreter = "sh"
    flag = "-c"


class AERubyRunner(AEScriptRunner):
    """Ruby 脚本执行器：ruby -e <script>"""

    interpreter = "ruby"
    flag = "-e"


# 脚本类型(AEScriptType) -> 执行器类
RUNNER_MAP: Dict[AEScriptType, Type[AEScriptRunner]] = {
    AEScriptType.python: AEPythonRunner,
    AEScriptType.shell: AEShellRunner,
    AEScriptType.ruby: AERubyRunner,
}


def get_runner(script_type: str) -> AEScriptRunner:
    """按脚本类型取执行器实例；未知类型抛 ValueError。"""
    cls = RUNNER_MAP.get(script_type)
    if cls is None:
        raise ValueError(f"未知脚本类型: {script_type!r}，应为 {tuple(RUNNER_MAP.keys())} 之一")
    return cls()
