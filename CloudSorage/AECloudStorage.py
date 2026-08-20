"""
AE Cloud Storage - 云存储提供商基类
对齐 llms/llm_providers/ae_base_provider.py 的写法：
公共方法统一打日志后委托抽象 _xxx；子类只需实现 _xxx。
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

    # ---- 抽象方法：各 provider 实现 ----

    @abstractmethod
    def _upload(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def _download(self, remote_path: str, local_path: str) -> str:
        pass

    @abstractmethod
    def _list_files(self, remote_dir: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def _delete(self, remote_path: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def _mkdir(self, remote_path: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def _exists(self, remote_path: str) -> bool:
        pass

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "loaded": self.is_loaded
        }
