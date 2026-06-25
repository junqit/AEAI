"""
AEScriptRunner - 脚本执行器接口（Protocol）
zsh / python / ruby 各自实现，只负责执行脚本内容并返回原始输出
"""
import os
import subprocess
from typing import Dict, Any, Protocol, runtime_checkable


@runtime_checkable
class AEScriptRunner(Protocol):
    """执行器接口协议"""

    runner_type: str

    def execute(self, content: str, args: list, env: dict, timeout: int) -> Dict[str, Any]: ...


class ZshRunner:

    runner_type: str = "zsh"

    def execute(self, content: str, args: list, env: dict, timeout: int) -> Dict[str, Any]:
        run_env = {**os.environ, **env}
        if os.path.isfile(content):
            cmd = ["zsh", content] + args
        else:
            cmd = ["zsh", "-c", content, "--"] + args

        result = subprocess.run(cmd, capture_output=True, text=True, env=run_env, timeout=timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


class PythonRunner:

    runner_type: str = "python"

    def execute(self, content: str, args: list, env: dict, timeout: int) -> Dict[str, Any]:
        run_env = {**os.environ, **env}
        if os.path.isfile(content):
            cmd = ["python3", content] + args
        else:
            cmd = ["python3", "-c", content] + args

        result = subprocess.run(cmd, capture_output=True, text=True, env=run_env, timeout=timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


class RubyRunner:

    runner_type: str = "ruby"

    def execute(self, content: str, args: list, env: dict, timeout: int) -> Dict[str, Any]:
        run_env = {**os.environ, **env}
        if os.path.isfile(content):
            cmd = ["ruby", content] + args
        else:
            cmd = ["ruby", "-e", content, "--"] + args

        result = subprocess.run(cmd, capture_output=True, text=True, env=run_env, timeout=timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
