"""
AE Baidu Storage - 百度网盘存储实现（基于 bypy 库）
构造零参，创建即自动连接百度网盘（用 ~/.bypy 缓存的 bypy OAuth token）。
appkey/secretkey 从环境变量 BAIDU_PAN_APPKEY/SECRETKEY 或 gitignore 的 credentials.py 读取。
首次使用前需用本应用 appkey 完成一次 OAuth 授权（用本类的授权入口，勿用 `python -m bypy`，
因其走 bypy 自带 app，token 与本应用不匹配）；之后构造即自动连接、非交互。

仅暴露增删改查：upload/download/list_files/delete/mkdir/exists。
bypy 客户端为内部私有（_bypy），外部不可直接操作。

路径语义：bypy 沙箱在 /apps/bypy/ 下，所有 remote_path 均相对该应用根目录；
base_path（环境变量 BAIDU_PAN_BASE_PATH）作为应用根下的子前缀。
"""
import os
from typing import List, Dict, Any

import bypy
from bypy import const

try:  # 作为 CloudSorage.baidu 包被导入
    from ..AECloudStorage import AECloudStorage
except ImportError:  # 以 CloudSorage 为根直接运行
    from AECloudStorage import AECloudStorage


class AEBaiduStorage(AECloudStorage):
    """百度网盘存储（bypy 实现）。创建即自动连接，仅暴露增删改查。"""

    def __init__(self):
        super().__init__()
        bp_env = (os.getenv("BAIDU_PAN_BASE_PATH") or "").strip("/")
        self.base_path = bp_env or None
        self._mute_bypy()
        self._bypy = bypy.ByPy(**self._appkey_kwargs())  # 创建即自动连接（授权用缓存 token）
        self.is_loaded = True

    @staticmethod
    def _appkey_kwargs():
        """appkey/secretkey：env > gitignore 的 credentials.py；缺省回落 bypy 自带 app"""
        appkey = os.getenv("BAIDU_PAN_APPKEY")
        secretkey = os.getenv("BAIDU_PAN_SECRETKEY")
        try:
            from . import credentials as _cred
            appkey = appkey or _cred.APPKEY
            secretkey = secretkey or _cred.SECRETKEY
        except ImportError:
            pass
        kw = {}
        if appkey:
            kw["apikey"] = appkey
        if secretkey:
            kw["secretkey"] = secretkey
        return kw

    @staticmethod
    def _mute_bypy():
        # bypy 是 CLI 库，默认往 stdout/stderr 打印进度与状态；库场景下静音
        import bypy.bypy as _bmod

        def _noop(*a, **k):
            return None

        for name in ("pr", "perr", "prcolor", "pprgr"):
            if hasattr(_bmod, name):
                setattr(_bmod, name, _noop)

    # ---- 路径处理（相对 bypy 应用根 /apps/bypy/）----

    def _full_path(self, remote_path: str) -> str:
        p = remote_path.lstrip("/")
        bp = (self.base_path or "").strip("/") or None
        if bp:
            return bp + "/" + p if p else bp
        return p

    def _check(self, result: int, op: str):
        """bypy 方法返回 int 错误码，0(ENoError) 为成功"""
        if result != const.ENoError:
            raise RuntimeError("[%s] bypy %s error code=%s" % (self.name, op, result))
        return result

    # ---- 增删改查 ----

    def _list_files(self, remote_dir: str) -> List[Dict[str, Any]]:
        path = self._full_path(remote_dir)
        bp = self._bypy
        before = len(bp.jsonq)
        result = bp.list(path)
        self._check(result, "list")
        files = []
        for j in list(bp.jsonq)[before:]:
            files.extend(j.get("list") or [])
        return files

    def _mkdir(self, remote_path: str) -> Dict[str, Any]:
        path = self._full_path(remote_path)
        result = self._bypy.mkdir(path)
        self._check(result, "mkdir")
        return {"errno": result, "remote": path}

    def _delete(self, remote_path: str) -> Dict[str, Any]:
        path = self._full_path(remote_path)
        result = self._bypy.delete(path)
        self._check(result, "delete")
        return {"errno": result, "remote": path}

    def _upload(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        path = self._full_path(remote_path)
        result = self._bypy.upload(local_path, path, ondup="overwrite")
        self._check(result, "upload")
        return {
            "errno": result,
            "local": local_path,
            "remote": path,
            "size": os.path.getsize(local_path),
        }

    def _download(self, remote_path: str, local_path: str) -> str:
        path = self._full_path(remote_path)
        parent = os.path.dirname(local_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        result = self._bypy.download(path, local_path)
        self._check(result, "download")
        return local_path

    def _exists(self, remote_path: str) -> bool:
        path = self._full_path(remote_path)
        result = self._bypy.get_file_info(path)
        return result == const.ENoError
