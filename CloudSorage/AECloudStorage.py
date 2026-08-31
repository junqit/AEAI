"""
AE Cloud Storage - 云存储提供商基类
对齐 llms/llm_providers/ae_base_provider.py 的写法：
公共方法统一打日志后委托 _xxx；子类按需覆写。
__init__ 接收 base_dir（基础目录），所有操作（upload/download/list/delete/mkdir/exists）
经 _resolve_path 解析后只能在此目录下进行。
_list_files 为必选（抽象）；_upload/_download/_delete/_mkdir/_exists 为可选，
默认抛 NotImplementedError，子类未覆写即不支持该操作。
"""
import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class AECloudStorage(ABC):
    """云存储提供商基类"""

    def __init__(self, base_dir: str):
        self.uid = uuid.uuid4().hex  # 唯一标识（string）
        self.name = self.__class__.__name__
        self.is_loaded = False
        self.base_dir = (base_dir or "/").rstrip("/") or "/"  # 基础目录：所有操作只能在此目录下进行

    def _resolve_path(self, remote_path: str) -> str:
        """将 remote_path 解析到 base_dir 下（所有操作只能在此目录下进行）。
        相对路径拼接到 base_dir；已在 base_dir 内的绝对路径原样；空/根返回 base_dir。"""
        base = self.base_dir
        if not remote_path or remote_path == "/":
            return base
        if remote_path == base or remote_path.startswith(base + "/"):
            return remote_path.rstrip("/") or base
        rp = remote_path.strip("/")
        return base + "/" + rp if rp else base

    # ---- 公共方法：打日志 + 委托抽象实现（镜像 AEBaseProvider.generate -> _generate）----

    def upload(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """上传本地文件到远程路径"""
        remote_path = self._resolve_path(remote_path)
        logger.info("[%s] upload local=%s remote=%s", self.name, local_path, remote_path)
        result = self._upload(local_path, remote_path)
        logger.info("[%s] upload result=%s", self.name,
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
        return result

    def download(self, remote_path: str, local_path: str) -> str:
        """下载远程文件到本地路径"""
        remote_path = self._resolve_path(remote_path)
        logger.info("[%s] download remote=%s local=%s", self.name, remote_path, local_path)
        result = self._download(remote_path, local_path)
        logger.info("[%s] download result=%s", self.name, result)
        return result

    def list_files(self, remote_dir: str) -> List[Dict[str, Any]]:
        """列出远程目录下的文件"""
        remote_dir = self._resolve_path(remote_dir)
        logger.info("[%s] list dir=%s", self.name, remote_dir)
        result = self._list_files(remote_dir)
        logger.info("[%s] list count=%s", self.name, len(result) if isinstance(result, list) else result)
        return result

    def delete(self, remote_path: str) -> Dict[str, Any]:
        """删除远程文件/目录"""
        remote_path = self._resolve_path(remote_path)
        logger.info("[%s] delete remote=%s", self.name, remote_path)
        result = self._delete(remote_path)
        logger.info("[%s] delete result=%s", self.name,
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
        return result

    def mkdir(self, remote_path: str) -> Dict[str, Any]:
        """创建远程目录"""
        remote_path = self._resolve_path(remote_path)
        logger.info("[%s] mkdir remote=%s", self.name, remote_path)
        result = self._mkdir(remote_path)
        logger.info("[%s] mkdir result=%s", self.name,
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
        return result

    def exists(self, remote_path: str) -> bool:
        """判断远程路径是否存在"""
        remote_path = self._resolve_path(remote_path)
        logger.info("[%s] exists remote=%s", self.name, remote_path)
        result = self._exists(remote_path)
        logger.info("[%s] exists result=%s", self.name, result)
        return result

    # ---- 子类实现的方法 ----
    # _list_files 必选（抽象）：provider 至少能列文件；
    # _upload/_download/_delete/_mkdir/_exists 可选，默认 NotImplementedError，子类按需覆写。

    @abstractmethod
    def _list_files(self, remote_dir: str) -> List[Dict[str, Any]]:
        pass

    def _upload(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        raise NotImplementedError("[%s] upload 未实现" % self.name)

    def _download(self, remote_path: str, local_path: str) -> str:
        raise NotImplementedError("[%s] download 未实现" % self.name)

    def _delete(self, remote_path: str) -> Dict[str, Any]:
        raise NotImplementedError("[%s] delete 未实现" % self.name)

    def _mkdir(self, remote_path: str) -> Dict[str, Any]:
        raise NotImplementedError("[%s] mkdir 未实现" % self.name)

    def _exists(self, remote_path: str) -> bool:
        raise NotImplementedError("[%s] exists 未实现" % self.name)

    def get_status(self) -> dict:
        return {
            "uid": self.uid,
            "name": self.name,
            "base_dir": self.base_dir,
            "loaded": self.is_loaded
        }
