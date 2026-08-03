import os
import shutil
import subprocess
import platform
import logging
from datetime import datetime
from typing import Dict, List, Optional

from .AEBaseContext import AEBaseContext
from .AEContextType import AEContextType
from .AELLMPayload import AEEnvParamType
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT

logger = logging.getLogger(__name__)


class AEDirectoryContext(AEBaseContext):
    """目录级 Context：提供系统/脚本环境探测、环境参数 prompt 构建与 role prompt 组装。"""

    # 可探测的脚本语言
    SCRIPT_LANGUAGES = ["ruby", "python", "zsh"]

    # 各环境参数类型的描述文本（prompt 静态部分）
    # 实际环境信息（OS / 脚本版本 / 已装库等）由 build_env_param_prompt 在描述之后追加，
    # 故描述中以“下方”指代随后拼接的真实探测信息，并要求据此确认可运行性。
    # 共用标注：环境信息仅在编写/执行软件程序（脚本）时参考，其他场景忽略。
    _ENV_PARAM_NOTE = "注：以下环境信息仅在需编写或执行软件程序（脚本/命令）时参考，其他场景可忽略。\n"
    ENV_PARAM_DESC: Dict[AEEnvParamType, str] = {
        AEEnvParamType.system: (
            _ENV_PARAM_NOTE
            + "【系统环境】下方为当前主机实际探测到的操作系统、硬件架构与系统级工具信息。"
            "据此确认所涉及的程序、脚本、工具在当前系统下可运行"
        ),
        AEEnvParamType.python: (
            _ENV_PARAM_NOTE
            + "【Python 环境】下方为当前实际可用的 Python 解释器版本、路径与已安装第三方库。"
            "所生成代码须确认仅使用下方已列出的解释器与库、可在当前环境下直接运行；"
            "缺失所需库时按安装申请规则申请安装，不得直接引用未安装的依赖。"
        ),
        AEEnvParamType.ruby: (
            _ENV_PARAM_NOTE
            + "【Ruby 环境】下方为当前实际可用的 Ruby 解释器版本、路径与已安装 gem 库。"
            "所生成代码须确认仅使用下方已列出的解释器与库、可在当前环境下直接运行；"
            "缺失所需库时按安装申请规则申请安装，不得直接引用未安装的依赖。"
        ),
        AEEnvParamType.shell: (
            _ENV_PARAM_NOTE
            + "【Shell 环境】下方为当前系统实际可用的 shell（如 zsh）及版本。"
            "所生成命令须确认可在当前 shell 环境下直接执行；"
            "所有文件与目录操作须限定在当前工作目录内。"
        ),
    }

    # 环境参数类型 -> 已探测脚本名称（system 无对应脚本，单独处理）
    _ENV_SCRIPT_NAME: Dict[AEEnvParamType, str] = {
        AEEnvParamType.python: "python",
        AEEnvParamType.ruby: "ruby",
        AEEnvParamType.shell: "zsh",
    }

    PACKAGE_COMMANDS = {
        "python": ["pip", "list", "--format=freeze"],
        "ruby": ["gem", "list", "--no-versions"],
        "node": ["npm", "list", "-g", "--depth=0", "--parseable"],
        "perl": ["cpan", "-l"],
        "php": ["composer", "global", "show", "--name-only"],
        "lua": ["luarocks", "list", "--porcelain"],
        "go": ["go", "list", "..."],
        "rust": ["cargo", "install", "--list"],
    }

    def __init__(self, space: str = ""):
        super().__init__(context_type=AEContextType.directory, space=space)
        self._scripts_cache: Optional[list] = None
        self._env_param_info_cache: Dict[AEEnvParamType, str] = {}
        # 创建后即探测并生成所有系统信息与脚本相关信息（缓存，后续直接复用）
        self._build_all_env_param_info()

    def _build_all_env_param_info(self) -> None:
        """创建时一次性探测并缓存所有环境参数信息（系统 + 所有脚本语言）。"""
        # 先探测脚本（system 不依赖脚本，但脚本类信息依赖此缓存）
        self._discover_scripts()
        for env_param in AEEnvParamType:
            self.build_env_param_info(env_param)

    # ==================== 环境参数（env_param）探测与 prompt 构建 ====================

    def _discover_scripts(self) -> list:
        """查找当前电脑内所有可用的脚本语言，结果缓存只执行一次"""
        if self._scripts_cache is not None:
            return self._scripts_cache
        scripts = []
        for name in self.SCRIPT_LANGUAGES:
            which = shutil.which(name)
            if which:
                scripts.append(self._get_script_info(name, which))
        self._scripts_cache = scripts
        return scripts

    def refresh_scripts(self):
        """外部触发重新扫描脚本信息"""
        self._scripts_cache = None
        self._env_param_info_cache.clear()
        self._build_all_env_param_info()

    def build_env_param_info(self, env_param: AEEnvParamType) -> str:
        """构建指定环境参数类型对应的当前系统实际信息（结果缓存，仅生成一次）。

        - system：OS / 架构 / 节点信息
        - python / ruby / shell：从已探测脚本中取对应项的版本、路径与已装库
        """
        if env_param in self._env_param_info_cache:
            return self._env_param_info_cache[env_param]
        info = self._generate_env_param_info(env_param)
        self._env_param_info_cache[env_param] = info
        return info

    def _generate_env_param_info(self, env_param: AEEnvParamType) -> str:
        """实际探测并拼接环境信息（每次调用都执行探测/拼接，由 build_env_param_info 缓存）。"""
        if env_param == AEEnvParamType.system:
            return (
                f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        name = self._ENV_SCRIPT_NAME.get(env_param)
        if not name:
            return ""
        scripts = self._discover_scripts()
        match = next((s for s in scripts if s["scriptname"] == name), None)
        if not match:
            return f"{name}: 未安装"
        parts = [f"{match['scriptname']} {match['version']} ({match['which']})"]
        if match["packages"]:
            parts.append(f"已安装库: {', '.join(match['packages'])}")
        return "\n".join(parts)

    def build_env_param_prompt(self, env_param: AEEnvParamType) -> str:
        """构建指定环境参数类型的完整 prompt：描述文本 + 当前系统实际信息拼接。"""
        desc = self.ENV_PARAM_DESC.get(env_param, "")
        info = self.build_env_param_info(env_param)
        if not info:
            return desc
        return f"{desc}\n{info}"

    @staticmethod
    def _subprocess_env() -> dict:
        """subprocess 环境变量，禁用 brew 自动更新等阻塞行为"""
        env = os.environ.copy()
        env["HOMEBREW_NO_AUTO_UPDATE"] = "1"
        env["HOMEBREW_NO_INSTALL_CLEANUP"] = "1"
        return env

    @staticmethod
    def _get_script_info(scriptname: str, which: str) -> dict:
        version = ""
        env = AEDirectoryContext._subprocess_env()
        try:
            result = subprocess.run(
                [scriptname, "--version"],
                capture_output=True, text=True, timeout=5, env=env
            )
            version = result.stdout.strip() or result.stderr.strip()
        except Exception:
            pass
        packages = AEDirectoryContext._get_packages(scriptname)
        return {"scriptname": scriptname, "which": which, "version": version, "packages": packages}

    @staticmethod
    def _get_packages(scriptname: str) -> list:
        """获取脚本语言已安装的库列表"""
        cmd = AEDirectoryContext.PACKAGE_COMMANDS.get(scriptname)
        if not cmd:
            return []
        if not shutil.which(cmd[0]):
            return []
        env = AEDirectoryContext._subprocess_env()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=env)
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                return [line.strip() for line in lines if line.strip()]
        except Exception:
            pass
        return []

    # ==================== role prompt 组装 ====================

    def build_system_prompt(self) -> str:
        """将当前系统信息和脚本信息组装为 role prompt"""
        sys_info = (
            f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
        )

        scripts = self._discover_scripts()
        script_parts = []
        for s in scripts:
            part = f"- {s['scriptname']} {s['version']} ({s['which']})"
            if s["packages"]:
                part += f"\n  已安装库: {', '.join(s['packages'])}"
            script_parts.append(part)

        if script_parts:
            scripts_info = "\n".join(script_parts)
        else:
            scripts_info = "当前无可用脚本语言。"

        install_instruction = """如果当前环境缺少完成任务所需的脚本语言或库，你可以申请安装。
申请时请严格按以下 JSON 结构输出：

{
  "action": "install_request",
  "packages": [
    {
      "scriptname": "需要安装的脚本语言或包管理器名称",
      "packages": ["需要安装的库名称列表"],
      "install_script": "根据当前系统环境生成的安装命令"
    }
  ],
  "reason": "安装原因说明"
}

注意：
- install_script 必须适配当前操作系统和架构。
- 仅在已有环境无法满足需求时才申请安装。
- 优先使用已安装的库。"""

        return (
            f"[当前系统环境]\n{sys_info}\n\n"
            f"[可用脚本语言及库]\n{scripts_info}\n\n"
            f"[安装申请规则]\n{install_instruction}"
        )

    ROLE = "你是用户的本地开发环境助手。你了解用户当前系统的操作系统、已安装的脚本语言和可用的库。回答问题时优先使用用户环境中已有的工具和库，不推荐用户未安装的依赖。"

    def build_role_prompt(self) -> dict:
        """组装完整的 role prompt，返回 {role: content} 结构"""
        system_info = self.build_system_prompt()
        prompt = f"[Role]\n{self.ROLE}\n\n{system_info}"
        from Roles.AERoleType import AEConentRole, AE_ROLE
        return {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: prompt}
