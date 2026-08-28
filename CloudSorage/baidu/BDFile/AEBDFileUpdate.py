"""
AE Baidu File Update - 百度网盘文件「改」能力（继承 AECloudFileUpdate）。
AEBaiduStorage 暂无 move/rename，默认未实现。不依赖 AEBDFile。
"""
try:  # 作为 CloudSorage.baidu.BDFile 包被导入
    from ...File.AECloudFileUpdate import AECloudFileUpdate
except ImportError:  # 以 CloudSorge 为根直接运行（baidu 作为顶层包）
    from File.AECloudFileUpdate import AECloudFileUpdate


class AEBDFileUpdate(AECloudFileUpdate):
    """百度网盘文件「改」：重命名/移动（暂未实现）。"""

    def update(self, new_name=None, new_path=None):
        raise NotImplementedError("update（rename/move）未实现：AEBaiduStorage 暂无 move/rename")
