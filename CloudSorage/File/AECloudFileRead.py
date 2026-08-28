"""
AECloudFile Read - 云盘文件的「查」能力（抽象，继承 AECloudFile）。

作为独立能力 mixin：仅声明 read，与 Create/Update/Delete 各自独立文件/类，
由具体云盘子类按需组合（多继承）并实现。
"""
from abc import ABC, abstractmethod
from typing import List

from .AECloudFile import AECloudFile


class AECloudFileRead(AECloudFile, ABC):
    """具备「查」能力的云盘文件：读取 / 查找 / 下载。"""

    @abstractmethod
    def read(self) -> List["AECloudFile"]:
        """查：读取本节点（文件夹列子项 / 文件取信息）"""
        ...

    @abstractmethod
    def find(self, key: str) -> List["AECloudFile"]:
        """查找：按 key 搜索文件"""
        ...

    @abstractmethod
    def download(self, local_path: str) -> str:
        """下载：下载本文件内容到 local_path"""
        ...
