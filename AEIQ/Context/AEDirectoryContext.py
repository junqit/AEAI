import os
import shutil
import subprocess
import platform
import logging
from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetRsp import AENetRspCode
from .AEBaseContext import AEBaseContext
from .AEContextPath import AE_PATH_CONTEXT_INFO
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

class AEDirectoryContext(AEBaseContext):

    SCRIPT_LANGUAGES = ["ruby", "python", "zsh"]

    PACKAGE_COMMANDS = {
        "python": ["pip", "list", "--format=freeze"],
        "python3": ["pip3", "list", "--format=freeze"],
        "ruby": ["gem", "list", "--no-versions"],
        "node": ["npm", "list", "-g", "--depth=0", "--parseable"],
        "perl": ["cpan", "-l"],
        "php": ["composer", "global", "show", "--name-only"],
        "lua": ["luarocks", "list", "--porcelain"],
        "go": ["go", "list", "..."],
        "rust": ["cargo", "install", "--list"],
    }

    def __init__(self, user=None, space: str = ""):
        super().__init__(context_type=AEContextType.directory, user=user, space=space)
        self._scripts_cache: list = None

    async def on_request(self, request: AENetReq) -> None:
        path = request.req.path if request.req else None

        if path == AE_PATH_CONTEXT_INFO:
            self._handle_info(request)
            return

        logger.info(f"AEDirectoryContext on_request: {request.model_dump_json(exclude_none=True)}")

    def _handle_info(self, request: AENetReq) -> None:
        cwd = os.getcwd()
        scripts = self._discover_scripts()
        info = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cwd": cwd,
            "scripts": scripts,
        }
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp=info,
            req=request.req,
            cont=request.cont,
            user=request.user
        )
        self.send_response(response)

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
        return self._scripts_cache

    def refresh_scripts(self):
        """外部触发重新扫描脚本信息"""
        self._scripts_cache = None
        self._discover_scripts()

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

    def build_system_prompt(self) -> str:
        """将当前系统信息和脚本信息组装为 role prompt"""
        sys_info = (
            f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
            f"Node: {platform.node()}\n"
            f"CWD: {os.getcwd()}"
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
        from Assistant.AERole import AERole
        return {"role": AERole.CONTEXT.value, "content": prompt}
