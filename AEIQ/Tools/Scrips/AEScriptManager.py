"""AEScriptManager - 脚本注册、执行管理，输出脚本定义的结果与本地运行的原始结果"""
import json
from typing import Dict, Any, Optional
from .AEScript import AEScript
from .AEScriptRunner import AEScriptRunner, ZshRunner, PythonRunner, RubyRunner


class AEScriptManager:

    def __init__(self):
        self._scripts: Dict[str, AEScript] = {}
        self._runners: Dict[str, AEScriptRunner] = {
            "zsh": ZshRunner(),
            "python": PythonRunner(),
            "ruby": RubyRunner(),
        }

    def register(self, script: AEScript) -> None:
        self._scripts[script.script_id] = script

    def get(self, script_id: str) -> Optional[AEScript]:
        return self._scripts.get(script_id)

    def list_scripts(self) -> list:
        return [
            {
                "script_id": s.script_id,
                "name": s.name,
                "description": s.description,
                "runner": s.runner,
                "input_schema": s.input_schema,
                "output_schema": s.output_schema,
            }
            for s in self._scripts.values()
        ]

    def run(self, script_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        script = self._scripts.get(script_id)
        if not script:
            return {"error": f"script '{script_id}' not found"}

        runner = self._runners.get(script.runner)
        if not runner:
            return {"error": f"unsupported runner '{script.runner}'"}

        args = inputs.get("args", [])
        env = inputs.get("env", {})
        timeout = inputs.get("timeout", 30)

        raw = runner.execute(script.content, args, env, timeout)

        output = self._parse_output(raw, script.output_schema)

        return {
            "script": {
                "script_id": script.script_id,
                "name": script.name,
                "output_schema": script.output_schema,
                "output": output,
            },
            "raw": raw,
        }

    def _parse_output(self, raw: Dict[str, Any], output_schema: dict) -> Optional[Dict[str, Any]]:
        """尝试从 stdout 解析脚本声明的 output_schema 结构"""
        stdout = raw.get("stdout", "")
        try:
            return json.loads(stdout.strip())
        except (json.JSONDecodeError, ValueError):
            return None
