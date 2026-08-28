"""
AECloudFile Update - 云盘文件的「改」能力（抽象，继承 AECloudFile）。

作为独立能力 mixin：仅声明 update，与 Create/Read/Delete 各自独立文件/类，
由具体云盘子类按需组合（多继承）并实现。
"""
from abc import ABC, abstractmethod
from typing import Optional

from .AECloudFile import AECloudFile


class AECloudFileUpdate(AECloudFile, ABC):
    """具备「改」能力的云盘文件：更新本节点（重命名 / 移动）。"""

    @abstractmethod
    def update(self, new_name: Optional[str] = None, new_path: Optional[str] = None) -> "AECloudFileUpdate":
        """改：更新本节点（重命名 / 移动）"""
        ...
