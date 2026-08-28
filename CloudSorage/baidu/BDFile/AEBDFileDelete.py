"""
AE Baidu File Delete - 百度网盘文件「删」能力（继承 AECloudFileDelete）。
纯能力 mixin：经 self.storage.delete 委托（AEBaiduStorage 当前由基类 NotImplementedError 兜底）。不依赖 AEBDFile。
"""
try:  # 作为 CloudSorage.baidu.BDFile 包被导入
    from ...File.AECloudFileDelete import AECloudFileDelete
except ImportError:  # 以 CloudSorge 为根直接运行（baidu 作为顶层包）
    from File.AECloudFileDelete import AECloudFileDelete


class AEBDFileDelete(AECloudFileDelete):
    """百度网盘文件「删」：删除本节点。委托 self.storage。"""

    def delete(self):
        if self.storage is None:
            raise RuntimeError("未绑定 storage：组合方需提供 storage 并 bind")
        return self.storage.delete(self.path or "")
