"""
AE Baidu File Create - 百度网盘文件「增」能力（继承 AECloudFileCreate）。
纯能力 mixin：经 self.storage（由组合方提供，如 AEBDFile + bind）委托 upload/mkdir。不依赖 AEBDFile。
"""
try:  # 作为 CloudSorage.baidu.BDFile 包被导入
    from ...File.AECloudFileCreate import AECloudFileCreate
except ImportError:  # 以 CloudSorge 为根直接运行（baidu 作为顶层包）
    from File.AECloudFileCreate import AECloudFileCreate


class AEBDFileCreate(AECloudFileCreate):
    """百度网盘文件「增」：文件夹→mkdir；文件→upload(local_path)。委托 self.storage。"""

    def create(self, local_path=None):
        if self.storage is None:
            raise RuntimeError("未绑定 storage：组合方需提供 storage 并 bind")
        path = self.path or ""
        if self.is_folder:
            return self.storage.mkdir(path)
        if not local_path:
            raise RuntimeError("创建文件需提供 local_path")
        return self.storage.upload(local_path, path)
