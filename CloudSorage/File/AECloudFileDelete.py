"""
AECloudFile Delete - 云盘文件的「删」能力（抽象，继承 AECloudFile）。

作为独立能力 mixin：仅声明 delete，与 Create/Read/Update 各自独立文件/类，
由具体云盘子类按需组合（多继承）并实现。
"""
from abc import ABC, abstractmethod
from typing import Any

from .AECloudFile import AECloudFile


class AECloudFileDelete(AECloudFile, ABC):
    """具备「删」能力的云盘文件：删除本节点。"""

    @abstractmethod
    def delete(self) -> Any:
        """删：删除本节点"""
        ...
