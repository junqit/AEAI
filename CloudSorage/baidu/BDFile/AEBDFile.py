"""
AE Baidu File - 百度网盘文件节点（继承 AEBDFileCreate/Read/Update/Delete，具备完整增删改查）。
组合 4 个 CRUD 能力 mixin（各自实现 create/read/find/download/update/delete）+ 提供 storage/bind；
经 bind(storage) 注入存储后 CRUD 方法可用。不直接继承 AECloudFile（经 4 个 mixin 间接继承）。
"""
from .AEBDFileCreate import AEBDFileCreate
from .AEBDFileRead import AEBDFileRead
from .AEBDFileUpdate import AEBDFileUpdate
from .AEBDFileDelete import AEBDFileDelete


class AEBDFile(AEBDFileCreate, AEBDFileRead, AEBDFileUpdate, AEBDFileDelete):
    """百度网盘文件节点（完整 CRUD）：继承 4 能力 mixin；经 bind(storage) 注入存储后 CRUD 可用。"""
    storage = None  # AEBaiduStorage，CRUD 方法经 bind 注入后使用

    def bind(self, storage) -> "AEBDFile":
        """绑定云盘存储，使 CRUD 方法可用"""
        self.storage = storage
        return self
