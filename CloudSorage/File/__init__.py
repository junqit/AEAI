"""
File - 云盘文件值对象与增删改查能力（各能力独立文件/类）。

AECloudFile 为纯值对象；AECloudFileCreate / AECloudFileRead / AECloudFileUpdate /
AECloudFileDelete 为各 CRUD 能力的抽象 mixin，由具体云盘子类按需组合（多继承）并实现。
"""
from .AECloudFile import AECloudFile
from .AECloudFileCreate import AECloudFileCreate
from .AECloudFileRead import AECloudFileRead
from .AECloudFileUpdate import AECloudFileUpdate
from .AECloudFileDelete import AECloudFileDelete

__all__ = ["AECloudFile", "AECloudFileCreate", "AECloudFileRead",
           "AECloudFileUpdate", "AECloudFileDelete"]
