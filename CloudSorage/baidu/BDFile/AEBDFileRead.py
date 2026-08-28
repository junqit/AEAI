"""
AE Baidu File Read - 百度网盘文件「查」能力（继承 AECloudFileRead）。
纯能力 mixin：经 self.storage 列子项（文件夹）；文件返回空列表。不依赖 AEBDFile。
"""
try:  # 作为 CloudSorage.baidu.BDFile 包被导入
    from ...File.AECloudFileRead import AECloudFileRead
    from ...File.AECloudFile import AECloudFile
except ImportError:  # 以 CloudSorge 为根直接运行（baidu 作为顶层包）
    from File.AECloudFileRead import AECloudFileRead
    from File.AECloudFile import AECloudFile


class AEBDFileRead(AECloudFileRead):
    """百度网盘文件「查」：读取/查找/下载。委托 self.storage。"""

    def read(self):
        if self.storage is None:
            raise RuntimeError("未绑定 storage：组合方需提供 storage 并 bind")
        if self.is_file:
            return []
        return [AECloudFile.from_dict(d) for d in self.storage.list_files(self.path or "") if isinstance(d, dict)]

    def find(self, key):
        if self.storage is None:
            raise RuntimeError("未绑定 storage：组合方需提供 storage 并 bind")
        return [AECloudFile.from_dict(d) for d in self.storage.search(key, self.path or "") if isinstance(d, dict)]

    def download(self, local_path):
        if self.storage is None:
            raise RuntimeError("未绑定 storage：组合方需提供 storage 并 bind")
        return self.storage.download(self.path or "", local_path)
