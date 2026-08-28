"""
AE Cloud File - 云盘文件值对象（通用，不绑定具体云盘厂商）。

为云盘「读取/列举」能力提供统一的结构化结果类型：一个 AECloudFile 表示云盘中的
一个文件或文件夹节点——类型 CloudFileType（FILE/FOLDER 枚举）、大小、内容标识 hash
（MD5 或 SHA，依厂商）、路径 path、父路径 parent，文件夹节点可通过 children 持有多个
子节点 AECloudFile（复合/树结构）。本类是纯值对象，不发起网络请求；列举由具体云盘
存储（如 AEBaiduStorage）负责。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CloudFileType(Enum):
    """云盘节点类型"""
    FILE = "file"
    FOLDER = "folder"


def _parent_of(path: Optional[str]) -> Optional[str]:
    """由完整路径推算父路径（云盘路径以 / 分隔）；根或无路径返回 None"""
    if not path:
        return None
    p = path.rstrip("/")
    if "/" not in p:
        return None  # 顶层（根下），无父
    return p.rsplit("/", 1)[0] or "/"


@dataclass
class AECloudFile:
    """云盘文件/文件夹节点。文件夹可经 children 持有子节点列表（复合结构）。"""
    name: str = ""
    type: CloudFileType = CloudFileType.FILE    # CloudFileType.FILE | CloudFileType.FOLDER
    size: int = 0                          # 字节数；文件夹通常为 0
    hash: Optional[str] = None            # 文件内容标识（MD5 或 SHA，依厂商）；文件夹可空
    path: Optional[str] = None             # 完整路径（可选）
    parent: Optional[str] = None          # 父路径（所属目录，可选）
    children: List["AECloudFile"] = field(default_factory=list)

    # ---- 判定 ----

    @property
    def is_folder(self) -> bool:
        return self.type == CloudFileType.FOLDER

    @property
    def is_file(self) -> bool:
        return self.type == CloudFileType.FILE

    # ---- 复合：子节点 ----

    def add_child(self, child: "AECloudFile") -> "AECloudFile":
        self.children.append(child)
        return child

    def child_count(self) -> int:
        return len(self.children)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AECloudFile":
        """从原始字段字典构造；容忍各厂商字段名差异（isdir/server_filename/md5/sha1 ...）。
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
            parent=data.get("parent") or _parent_of(path),
        )
