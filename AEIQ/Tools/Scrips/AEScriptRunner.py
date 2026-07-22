"""
AEScriptRunner - 脚本执行器：python / shell / ruby 三种。

每种执行器以对应解释器运行脚本内容（AEScript.script），返回 stdout。
执行器本身不持有脚本，仅负责执行；由外部按 AEScript.type 选用。
"""
import subprocess
from typing import Dict, Type, Optional

from .AEScript import AEScript, AEScriptType


class AEScriptRunner:
    """脚本执行器基类：以 [interpreter, flag, script_content] 方式运行脚本。"""

    # 子类覆写：解释器命令与脚本传入 flag
    interpreter: str = ""
    flag: str = ""

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
