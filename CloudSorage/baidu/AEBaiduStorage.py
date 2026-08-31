"""
AE Baidu Storage - 百度网盘文件操作（直连百度网盘 OpenAPI，不再依赖 bypy）。

凭证（应用凭证 + OAuth token）与一切 Credential 能力（加载/判断/持久化/刷新/授权/
取有效 token）均由 AEBDCredential 提供；本类只负责网盘文件操作：文件列表、上传、
创建文件夹、用户信息。不读环境变量，不含任何凭证逻辑。

构造需 4 凭证参数（app_name/app_key/app_secret/credential_path），非交互；过期则 cred.refresh() 续期。
首次使用前需调用一次 s.cred.authorize() 完成 device-code 授权；之后构造即自动连接。

实现范围（其余存储操作由 AECloudStorage 基类提供 NotImplementedError 默认）：
  - 文件列表访问：xpanfilelist（_list_files，自动翻页）
  - 创建文件夹：_mkdir（precreate isdir=1 + create，无分片）
  - 上传文件：_upload（precreate → superfile2 按 4MB 分片 → create）
  - 用户信息：get_user_info（xpannasuinfo）
未实现（基类默认 NotImplementedError）：download/delete/exists。

沙箱（重要）：自 2026-08-31 起应用默认仅可访问 /apps/{APP_NAME}/ 目录
（APP_NAME 取自 credentials.APP_NAME，缺省 FileManager）。所有 remote_path 相对该沙箱根
解析：API 实际路径 = /apps/{APP_NAME}[/base_path]/remote_path。
"""
import hashlib
import json
import os
from typing import List, Dict, Any

import requests

try:  # 作为 CloudSorage.baidu 包被导入
    from ..AECloudStorage import AECloudStorage
    from ..File.AECloudFile import CloudFileType
except ImportError:  # 以 CloudSorge 为根直接运行（baidu 作为顶层包）
    from AECloudStorage import AECloudStorage
    from File.AECloudFile import CloudFileType
from .AEBDCredential import AEBDCredential  # 同包，单点相对导入两种上下文均可用
from .BDFile import AEBDFile

# ---- 百度网盘端点（pan.baidu.com / d.pcs.baidu.com）----
_PAN_HOST = "https://pan.baidu.com"
_URL_FILE = _PAN_HOST + "/rest/2.0/xpan/file"                 # ?method=<list|precreate|create|filemanager>&...&openapi=xpansdk
_URL_UINFO = _PAN_HOST + "/rest/2.0/xpan/nas"                 # ?method=uinfo&openapi=xpansdk
_URL_SUPERFILE = "https://d.pcs.baidu.com/rest/2.0/pcs/superfile2"  # ?method=upload&openapi=xpansdk
_URL_DOWNLOAD = "https://d.pcs.baidu.com/rest/2.0/pcs/file"        # ?method=download&access_token&path（PCS 按路径下载）

# 单页文件数上限（xpanfilelist method=list 的 limit）
_PAGE_LIMIT = 1000
# 上传：superfile2 单片 4MB；rtype 重名策略对齐 SDK demo 取 3
_UPLOAD_CHUNK = 4 * 1024 * 1024
_UPLOAD_RTYPE = 3
# 下载流式分片
_DOWNLOAD_CHUNK = 1024 * 1024


class AEBaiduStorage(AECloudStorage):
    """百度网盘文件操作。凭证与 OAuth 能力全部委托 AEBDCredential。"""

    def __init__(self, app_name: str, app_key: str, app_secret: str, credential_path: str):
        self._cred = AEBDCredential(app_name, app_key, app_secret, credential_path)
        self._cred.delegate = self  # 注册为 delegate，接收验证有效/刷新成功回调
        self.app_name = app_name
        self.sandbox_root = "/apps/" + app_name  # 沙箱根（2026-08-31 起强制）
        super().__init__(base_dir=self.sandbox_root)  # 基础目录 = 沙箱根
        self.token_path = credential_path
        self.files: List[AEBDFile] = []
        # 验证有效/刷新成功 → 回调 on_valid/on_refreshed → 添加第一个 AEBDFile
        self.is_loaded = self._cred.verify()

    # ---- 凭证访问 ----

    @property
    def cred(self) -> AEBDCredential:
        """凭证对象；authorize/authorize_with_code/refresh 等能力由它提供"""
        return self._cred

    # ---- AEBDCredential delegate 回调 ----

    def on_valid(self, cred: AEBDCredential) -> None:
        """credential 验证有效（含授权后有效）：标记已加载 + 添加第一个 AEBDFile"""
        self.is_loaded = True
        self._add_first_file()

    def on_refreshed(self, cred: AEBDCredential) -> None:
        """credential 刷新成功：标记已加载 + 添加第一个 AEBDFile（幂等）"""
        self.is_loaded = True
        self._add_first_file()

    def _add_first_file(self) -> None:
        """添加第一个 AEBDFile（沙箱根节点）；幂等，仅一次"""
        if self.files:
            return
        self.files.append(AEBDFile(name=self.app_name, type=CloudFileType.FOLDER, path=self.sandbox_root))

    # ---- HTTP（网盘文件操作：GET/POST/分片）----

    @staticmethod
    def _request(method: str, url: str, params=None, data=None, files=None, timeout=30) -> dict:
        resp = requests.request(method, url, params=params, data=data, files=files, timeout=timeout)
        try:
            return resp.json()
        except ValueError:
            raise RuntimeError(
                "百度 OpenAPI 非 JSON 响应 status=%s body=%s"
                % (resp.status_code, resp.text[:200]))

    # ---- 用户信息 ----

    def get_user_info(self) -> dict:
        """xpannasuinfo：返回授权用户信息（errno/uk/baidu_name/netdisk_name/vip_type/...）"""
        access_token = self._cred.get_access_token()
        return self._request("GET", _URL_UINFO, params={
            "method": "uinfo", "openapi": "xpansdk", "access_token": access_token,
        })

    # ---- 文件列表访问（xpanfilelist）----

    def _list_files(self, remote_dir: str) -> List[Dict[str, Any]]:
        access_token = self._cred.get_access_token()
        dir_path = remote_dir
        files: List[Dict[str, Any]] = []
        start = 0
        while True:
            r = self._request("GET", _URL_FILE, params={
                "method": "list", "openapi": "xpansdk", "access_token": access_token,
                "dir": dir_path, "order": "time", "desc": 1,
                "start": start, "limit": _PAGE_LIMIT, "web": "web", "showempty": 1,
            })
            errno = r.get("errno")
            if errno not in (None, 0):
                raise RuntimeError(
                    "[%s] xpanfilelist errno=%s %s" % (self.name, errno, r.get("errmsg", "")))
            batch = r.get("list") or []
            files.extend(batch)
            if len(batch) < _PAGE_LIMIT:
                break
            start += _PAGE_LIMIT
        return files

    def print_file_list(self, remote_dir: str) -> List[Dict[str, Any]]:
        """打印目录下的文件列表（目录路径 + 每项 DIR/FILE、名称、大小），并返回该列表"""
        files = self.list_files(remote_dir)
        print("目录: %s （共 %d 项）" % (self._resolve_path(remote_dir), len(files)))
        for f in files:
            tag = "DIR " if f.get("isdir") else "FILE"
            name = f.get("server_filename") or f.get("path", "")
            print("  %s %s  size=%s" % (tag, name, f.get("size", "")))
        return files

    # ---- 上传文件 / 创建文件夹（fileupload：precreate → superfile2 分片 → create）----

    @staticmethod
    def _md5_blocks(local_path: str):
        """按 4MB 分片读文件，返回 (block_list, n)：block_list 为 md5 hex 的 JSON 串"""
        md5s = []
        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                md5s.append(hashlib.md5(chunk).hexdigest())
        if not md5s:  # 空文件：单个空块（md5=d41d8cd98f00b204e9800998ecf8427e）
            md5s.append(hashlib.md5(b"").hexdigest())
        return json.dumps(md5s, ensure_ascii=False), len(md5s)

    def _upload(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        access_token = self._cred.get_access_token()
        path = remote_path
        size = os.path.getsize(local_path)
        block_list, n_blocks = self._md5_blocks(local_path)
        # 1. precreate（access_token 走 query，path/isdir/size/autoinit/block_list/rtype 走 form）
        pre = self._request("POST", _URL_FILE, params={
            "method": "precreate", "openapi": "xpansdk", "access_token": access_token,
        }, data={
            "path": path, "isdir": 0, "size": size, "autoinit": 1,
            "block_list": block_list, "rtype": _UPLOAD_RTYPE,
        })
        uploadid = pre.get("uploadid")
        if not uploadid:
            raise RuntimeError("[%s] upload precreate 失败: %s" % (self.name, pre))
        # 2. superfile2 分片上传（access_token/partseq/path/uploadid/type 走 query，file 走 multipart）
        with open(local_path, "rb") as f:
            for partseq in range(n_blocks):
                chunk = f.read(_UPLOAD_CHUNK)
                cr = self._request("POST", _URL_SUPERFILE, params={
                    "method": "upload", "openapi": "xpansdk", "access_token": access_token,
                    "partseq": str(partseq), "path": path, "uploadid": uploadid, "type": "tmpfile",
                }, files={"file": (os.path.basename(path), chunk)}, timeout=120)
                if not cr.get("md5") and cr.get("errno") not in (None, 0):
                    raise RuntimeError(
                        "[%s] upload superfile2 partseq=%s 失败: %s" % (self.name, partseq, cr))
        # 3. create（与 precreate 的 path/size/block_list 保持一致）
        cre = self._request("POST", _URL_FILE, params={
            "method": "create", "openapi": "xpansdk", "access_token": access_token,
        }, data={
            "path": path, "isdir": 0, "size": size, "uploadid": uploadid,
            "block_list": block_list, "rtype": _UPLOAD_RTYPE,
        })
        errno = cre.get("errno")
        if errno not in (None, 0):
            raise RuntimeError(
                "[%s] upload create 失败 errno=%s %s" % (self.name, errno, cre.get("errmsg", "")))
        return {
            "errno": errno if errno is not None else 0,
            "local": local_path, "remote": path, "size": size, "raw": cre,
        }

    def _mkdir(self, remote_path: str) -> Dict[str, Any]:
        access_token = self._cred.get_access_token()
        path = remote_path
        block_list = "[]"  # 文件夹无分片
        # 1. precreate（isdir=1, size=0）
        pre = self._request("POST", _URL_FILE, params={
            "method": "precreate", "openapi": "xpansdk", "access_token": access_token,
        }, data={
            "path": path, "isdir": 1, "size": 0, "autoinit": 1,
            "block_list": block_list, "rtype": _UPLOAD_RTYPE,
        })
        uploadid = pre.get("uploadid")
        if not uploadid:
            raise RuntimeError("[%s] mkdir precreate 失败: %s" % (self.name, pre))
        # 2. create（isdir=1, 无分片上传）
        cre = self._request("POST", _URL_FILE, params={
            "method": "create", "openapi": "xpansdk", "access_token": access_token,
        }, data={
            "path": path, "isdir": 1, "size": 0, "uploadid": uploadid,
            "block_list": block_list, "rtype": _UPLOAD_RTYPE,
        })
        errno = cre.get("errno")
        if errno not in (None, 0):
            raise RuntimeError(
                "[%s] mkdir create 失败 errno=%s %s" % (self.name, errno, cre.get("errmsg", "")))
        return {"errno": errno if errno is not None else 0, "remote": path, "raw": cre}

    # ---- 查找文件（xpanfilesearch）----

    def search(self, key: str, remote_dir: str = None, recursion: int = 1) -> List[Dict[str, Any]]:
        """按 key 搜索文件；remote_dir 限定目录（缺省全网盘）。返回原始条目列表。"""
        access_token = self._cred.get_access_token()
        params = {
            "method": "search", "openapi": "xpansdk", "access_token": access_token,
            "key": key, "recursion": str(recursion),
        }
        if remote_dir:
            params["dir"] = self._resolve_path(remote_dir)
        r = self._request("GET", _URL_FILE, params=params)
        errno = r.get("errno")
        if errno not in (None, 0):
            raise RuntimeError("[%s] search errno=%s %s" % (self.name, errno, r.get("errmsg", "")))
        return r.get("list") or []

    # ---- 下载文件（PCS 按路径下载，流式）----

    def _download(self, remote_path: str, local_path: str) -> str:
        access_token = self._cred.get_access_token()
        path = remote_path
        parent = os.path.dirname(local_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        resp = requests.get(_URL_DOWNLOAD, params={
            "method": "download", "access_token": access_token, "path": path,
        }, stream=True, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError("[%s] download 失败 status=%s" % (self.name, resp.status_code))
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(_DOWNLOAD_CHUNK):
                if chunk:
                    f.write(chunk)
        return local_path
