"""
AE Cloud Storage - 云存储提供商基类
对齐 llms/llm_providers/ae_base_provider.py 的写法：
公共方法统一打日志后委托 _xxx；子类按需覆写。
_list_files 为必选（抽象）；_upload/_download/_delete/_mkdir/_exists 为可选，
默认抛 NotImplementedError，子类未覆写即不支持该操作。
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class AECloudStorage(ABC):
    """云存储提供商基类"""

    def __init__(self):
        self.name = self.__class__.__name__
        self.is_loaded = False

    # ---- 公共方法：打日志 + 委托抽象实现（镜像 AEBaseProvider.generate -> _generate）----

    def upload(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """上传本地文件到远程路径"""
        logger.info("[%s] upload local=%s remote=%s", self.name, local_path, remote_path)
        result = self._upload(local_path, remote_path)
        logger.info("[%s] upload result=%s", self.name,
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
        return result

    def download(self, remote_path: str, local_path: str) -> str:
        """下载远程文件到本地路径"""
        logger.info("[%s] download remote=%s local=%s", self.name, remote_path, local_path)
        result = self._download(remote_path, local_path)
        logger.info("[%s] download result=%s", self.name, result)
        return result

    def list_files(self, remote_dir: str) -> List[Dict[str, Any]]:
        """列出远程目录下的文件"""
        logger.info("[%s] list dir=%s", self.name, remote_dir)
        result = self._list_files(remote_dir)
        logger.info("[%s] list count=%s", self.name, len(result) if isinstance(result, list) else result)
        return result

    def delete(self, remote_path: str) -> Dict[str, Any]:
        """删除远程文件/目录"""
        logger.info("[%s] delete remote=%s", self.name, remote_path)
        result = self._delete(remote_path)
        logger.info("[%s] delete result=%s", self.name,
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
        return result

    def mkdir(self, remote_path: str) -> Dict[str, Any]:
        """创建远程目录"""
        logger.info("[%s] mkdir remote=%s", self.name, remote_path)
        result = self._mkdir(remote_path)
        logger.info("[%s] mkdir result=%s", self.name,
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
        return result

    def exists(self, remote_path: str) -> bool:
        """判断远程路径是否存在"""
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
            "name": self.name,
            "loaded": self.is_loaded
        }
