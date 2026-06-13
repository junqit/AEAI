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
        """查找当前电脑内所有可用的脚本语言"""
        scripts = []
        for name in self.SCRIPT_LANGUAGES:
            which = shutil.which(name)
            if which:
                scripts.append(self._get_script_info(name, which))
        return scripts

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
