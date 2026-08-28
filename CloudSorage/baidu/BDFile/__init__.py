"""
BDFile - 百度网盘文件值对象与增删改查能力（各能力独立文件/类）。
AEBDFile 为纯值对象（继承 AECloudFile，可 bind storage）；AEBDFileCreate/Read/Update/Delete
为各 CRUD 能力的纯 mixin（继承对应 File/ mixin，不依赖 AEBDFile），由组合方按需多继承。
"""
from .AEBDFile import AEBDFile
from .AEBDFileCreate import AEBDFileCreate
from .AEBDFileRead import AEBDFileRead
from .AEBDFileUpdate import AEBDFileUpdate
from .AEBDFileDelete import AEBDFileDelete

__all__ = ["AEBDFile", "AEBDFileCreate", "AEBDFileRead", "AEBDFileUpdate", "AEBDFileDelete"]
