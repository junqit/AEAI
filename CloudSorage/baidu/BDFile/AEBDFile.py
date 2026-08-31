"""
AE Baidu File - 百度网盘文件节点（继承 AEBDFileCreate/Read/Update/Delete，具备完整增删改查）。
组合 4 个 CRUD 能力 mixin + storage 属性；storage 注入后 CRUD 方法可用。
from_dict 由本类实现（百度字段适配：isdir/server_filename/filename/md5/path ...）。
"""
from typing import Any, Dict

from .AEBDFileCreate import AEBDFileCreate
from .AEBDFileRead import AEBDFileRead
from .AEBDFileUpdate import AEBDFileUpdate
from .AEBDFileDelete import AEBDFileDelete

try:  # 作为 CloudSorage.baidu.BDFile 包被导入
    from ...File.AECloudFile import CloudFileType
except ImportError:  # 以 CloudSorge 为根直接运行（baidu 作为顶层包）
    from File.AECloudFile import CloudFileType


class AEBDFile(AEBDFileCreate, AEBDFileRead, AEBDFileUpdate, AEBDFileDelete):
    """百度网盘文件节点（完整 CRUD）：继承 4 能力 mixin；storage 注入后 CRUD 可用。"""
    storage = None  # AEBaiduStorage，CRUD 方法经 storage 属性注入后使用

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AEBDFile":
        """从百度 API 字段字典构造（isdir/server_filename/filename/md5/sha/path ...）。
        parent 缺省时由 path 推算。"""
        isdir = data.get("isdir")
        if isdir is None:
            isdir = data.get("is_dir") or data.get("type") == "folder"
        path = data.get("path")
        return cls(
            name=data.get("name") or data.get("server_filename") or data.get("filename") or "",
            type=CloudFileType.FOLDER if isdir else CloudFileType.FILE,
            size=int(data.get("size") or 0),
            hash=data.get("md5") or data.get("sha") or data.get("sha1"),
            path=path,
            parent=data.get("parent") or cls._parent_of(path),
        )
