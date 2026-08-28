"""
AECloudFile Create - 云盘文件的「增」能力（抽象，继承 AECloudFile）。

作为独立能力 mixin：仅声明 create，与 Read/Update/Delete 各自独立文件/类，
由具体云盘子类按需组合（多继承）并实现。
"""
from abc import ABC, abstractmethod
from typing import Any, Optional

from .AECloudFile import AECloudFile


class AECloudFileCreate(AECloudFile, ABC):
    """具备「增」能力的云盘文件：创建本节点（文件上传 / 文件夹新建）。"""

    @abstractmethod
    def create(self, local_path: Optional[str] = None) -> Any:
        """增：创建本节点（文件夹→mkdir；文件→upload(local_path)）"""
        ...
