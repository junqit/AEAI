"""
AE Baidu Storage - 百度网盘存储实现（直连百度网盘 OpenAPI，不再依赖 bypy）

访问流程对齐百度官方 OpenAPI Python SDK（pythonsdk_20220616/openapi_client/api/*.py）：
  - OAuth：device-code 授权（/oauth/2.0/device/code → 轮询 /oauth/2.0/token?grant_type=device_token）
           + refresh_token 自动续期（grant_type=refresh_token）
           + authorization-code 备选入口（grant_type=authorization_code）
  - 网盘文件：xpanfilelist（/rest/2.0/xpan/file?method=list）等

构造零参、非交互：创建时从本地 token 缓存加载 access_token，过期则用 refresh_token
自动续期。首次使用前需调用一次 authorize() 完成 device-code 授权（打印验证 URL/二维码
→ 用户授权 → 轮询拿 token 并缓存）；之后构造即自动连接、非交互。

appkey/secretkey/app_name 从 gitignore 的 credentials.py 读取（对应 OpenAPI 的
client_id/client_secret、应用沙箱名）；不读环境变量。

本次实现范围（仅授权的「用户验证 + 文件列表访问」；其余存储操作不在本类，
由 AECloudStorage 基类提供 NotImplementedError 默认，调用即报未实现）：
  - 用户验证：device-code OAuth（authorize/authorize_with_code）+ refresh_token
              自动续期 + xpannasuinfo 取用户信息（get_user_info）
  - 文件列表访问：xpanfilelist（_list_files，自动翻页）
未实现（基类默认 NotImplementedError）：upload/download/delete/mkdir/exists。

token 缓存：默认 ~/.baidu_pan/token.json（可用 credentials.TOKEN_PATH 覆盖），权限 0600。

沙箱（重要）：自 2026-08-31 起百度平台强制应用默认仅可访问 /apps/{APP_NAME}/ 目录
（本应用 APP_NAME=FileManager）。所有 remote_path 均相对该沙箱根解析：
API 实际路径 = /apps/{APP_NAME}[/base_path]/remote_path。APP_NAME 取自
credentials.APP_NAME，缺省 "FileManager"；base_path（credentials.BASE_PATH，可选）
作为沙箱内统一子前缀。
"""
import json
import os
import time
from typing import List, Dict, Any, Tuple

import requests

try:  # 作为 CloudSorage.baidu 包被导入
    from ..AECloudStorage import AECloudStorage
except ImportError:  # 以 CloudSorage 为根直接运行
    from AECloudStorage import AECloudStorage

# ---- 百度 OpenAPI 端点（来自 pythonsdk_20220616/openapi_client/api/*.py）----
_OPENAPI_HOST = "https://openapi.baidu.com"   # OAuth 授权域
_PAN_HOST = "https://pan.baidu.com"            # 网盘文件操作域

# OAuth（openapi.baidu.com）
_URL_DEVICE_CODE = _OPENAPI_HOST + "/oauth/2.0/device/code"   # ?response_type=device_code&openapi=xpansdk
_URL_TOKEN = _OPENAPI_HOST + "/oauth/2.0/token"              # ?grant_type=<device_token|authorization_code|refresh_token>&openapi=xpansdk
# 网盘（pan.baidu.com）
_URL_FILE = _PAN_HOST + "/rest/2.0/xpan/file"                 # ?method=<list|filemanager>&opera=<delete|...>&openapi=xpansdk
_URL_UINFO = _PAN_HOST + "/rest/2.0/xpan/nas"                 # ?method=uinfo&openapi=xpansdk

_DEFAULT_SCOPE = "basic,netdisk"
_TOKEN_DIR = os.path.expanduser("~/.baidu_pan")
_DEFAULT_TOKEN_PATH = os.path.join(_TOKEN_DIR, "token.json")

# 距过期不足此秒数即提前 refresh，避免边界过期
_REFRESH_MARGIN = 60
# 单页文件数上限（xpanfilelist method=list 的 limit）
_PAGE_LIMIT = 1000


class AEBaiduStorage(AECloudStorage):
    """百度网盘存储（直连 OpenAPI）。创建即自动加载/续期 token；首次需 authorize()。"""

    def __init__(self):
        super().__init__()
        self.base_path = (str(self._cred_attr("BASE_PATH") or "").strip("/")) or None
        self.app_name = self._cred_attr("APP_NAME") or "FileManager"
        self.sandbox_root = "/apps/" + self.app_name  # 沙箱根（2026-08-31 起强制）
        self.token_path = self._cred_attr("TOKEN_PATH") or _DEFAULT_TOKEN_PATH
        self._token = None  # {access_token, refresh_token, expires_at, scope}
        self._load_token()
        # 构造即自动连接：token 过期但有 refresh_token 则静默续期
        if self._token and not self._is_token_valid() and self._token.get("refresh_token"):
            try:
                self._refresh()
            except RuntimeError:
                pass  # 续期失败留待 _access_token() 抛错指引 authorize()
        self.is_loaded = self._is_token_valid()

    # ---- 配置：仅从 gitignore 的 credentials.py 读取（不读环境变量）----

    @staticmethod
    def _cred_attr(name: str, default=None):
        """从 credentials.py 取属性；文件缺省或属性不存在则返回 default"""
        try:
            from . import credentials as _cred
            return getattr(_cred, name, default)
        except ImportError:
            return default

    @staticmethod
    def _credentials() -> Tuple[str, str]:
        """返回 (client_id, client_secret) = (APPKEY, SECRETKEY)"""
        return AEBaiduStorage._cred_attr("APPKEY"), AEBaiduStorage._cred_attr("SECRETKEY")

    # ---- token 缓存 ----

    def _load_token(self):
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = None
        self._token = data

    def _save_token(self, token: dict):
        """用 OAuth 返回（含 access_token/refresh_token/expires_in/scope）更新并落盘缓存"""
        access_token = token.get("access_token")
        if not access_token:
            raise RuntimeError("OAuth 返回缺少 access_token: %s" % token)
        expires_in = token.get("expires_in")
        # refresh_token 缺省保留旧值（refresh 响应可能不含）
        refresh_token = token.get("refresh_token") or (self._token or {}).get("refresh_token")
        self._token = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": int(time.time()) + int(expires_in) if expires_in else 0,
            "scope": token.get("scope"),
        }
        try:
            os.makedirs(os.path.dirname(self.token_path) or ".", exist_ok=True)
            with open(self.token_path, "w", encoding="utf-8") as f:
                json.dump(self._token, f, ensure_ascii=False, indent=2)
                f.flush()
            os.chmod(self.token_path, 0o600)
        except OSError:
            pass  # 缓存落盘失败不阻断内存中的 token

    def _is_token_valid(self) -> bool:
        t = self._token
        if not (t and t.get("access_token")):
            return False
        exp = t.get("expires_at", 0)
        return not exp or exp - _REFRESH_MARGIN > int(time.time())

    # ---- HTTP ----

    @staticmethod
    def _request(method: str, url: str, params=None, data=None) -> dict:
        resp = requests.request(method, url, params=params, data=data, timeout=30)
        try:
            return resp.json()
        except ValueError:
            raise RuntimeError(
                "百度 OpenAPI 非 JSON 响应 status=%s body=%s"
                % (resp.status_code, resp.text[:200]))

    def _access_token(self) -> str:
        """取有效 access_token；过期则用 refresh_token 续期，失败抛错指引 authorize()"""
        if self._is_token_valid():
            return self._token["access_token"]
        if self._token and self._token.get("refresh_token"):
            self._refresh()
            if self._is_token_valid():
                self.is_loaded = True
                return self._token["access_token"]
        self.is_loaded = False
        raise RuntimeError("百度网盘未授权或 token 已失效，请先调用 authorize() 完成授权")

    # ---- 用户验证 ----

    def authorize(self, scope: str = _DEFAULT_SCOPE, timeout: int = 600) -> dict:
        """device-code OAuth 授权（交互式，首次使用调用一次）。

        流程：取 device_code → 打印 verification_url/qrcode_url + user_code →
        轮询 device_token 端点，用户完成授权后拿到 access_token/refresh_token → 缓存。
        """
        client_id, client_secret = self._credentials()
        if not (client_id and client_secret):
            raise RuntimeError(
                "缺少 client_id/client_secret：在 credentials.py 设置 APPKEY/SECRETKEY")
        # 1. 取 device code（仅需 client_id）
        d = self._request("GET", _URL_DEVICE_CODE, params={
            "response_type": "device_code", "openapi": "xpansdk",
            "client_id": client_id, "scope": scope,
        })
        device_code = d.get("device_code")
        if not device_code:
            raise RuntimeError("获取 device_code 失败: %s" % d)
        user_code = d.get("user_code", "")
        verification_url = d.get("verification_url", "")
        qrcode_url = d.get("qrcode_url", "")
        interval = max(int(d.get("interval", 5) or 5), 1)
        expires_in = int(d.get("expires_in", 600) or 600)
        print("\n[百度网盘授权] 请在浏览器访问: %s" % verification_url)
        if user_code:
            print("[百度网盘授权] 授权码: %s" % user_code)
        if qrcode_url:
            print("[百度网盘授权] 或扫码: %s" % qrcode_url)
        print("[百度网盘授权] 等待授权完成...")
        # 2. 轮询 device token（需 client_id + client_secret）
        deadline = int(time.time()) + min(expires_in, timeout)
        while int(time.time()) < deadline:
            r = self._request("GET", _URL_TOKEN, params={
                "grant_type": "device_token", "openapi": "xpansdk",
                "code": device_code, "client_id": client_id, "client_secret": client_secret,
            })
            if r.get("access_token"):
                self._save_token(r)
                self.is_loaded = True
                print("[百度网盘授权] 成功，token 已缓存到 %s" % self.token_path)
                return r
            # 用户尚未授权：按 interval 重试；遇 fatal 错误（过期/拒绝）立即终止
            err = str(r.get("error") or r.get("errmsg") or "")
            if err and ("expired" in err or "denied" in err):
                raise RuntimeError("device-code 授权失败: %s" % r)
            time.sleep(interval)
        raise RuntimeError("device-code 授权超时，未在 %ss 内完成授权" % timeout)

    def authorize_with_code(self, code: str, redirect_uri: str = "oob") -> dict:
        """authorization-code OAuth 授权（备选：用浏览器回调/粘贴的 code 换 token）"""
        client_id, client_secret = self._credentials()
        if not (client_id and client_secret):
            raise RuntimeError(
                "缺少 client_id/client_secret：在 credentials.py 设置 APPKEY/SECRETKEY")
        r = self._request("GET", _URL_TOKEN, params={
            "grant_type": "authorization_code", "openapi": "xpansdk",
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        })
        if not r.get("access_token"):
            raise RuntimeError("authorization_code 换 token 失败: %s" % r)
        self._save_token(r)
        self.is_loaded = True
        return r

    def _refresh(self) -> dict:
        """用 refresh_token 续期 access_token"""
        client_id, client_secret = self._credentials()
        refresh_token = (self._token or {}).get("refresh_token")
        if not (client_id and client_secret and refresh_token):
            raise RuntimeError("refresh_token 续期缺参数（client_id/client_secret/refresh_token）")
        r = self._request("GET", _URL_TOKEN, params={
            "grant_type": "refresh_token", "openapi": "xpansdk",
            "refresh_token": refresh_token, "client_id": client_id, "client_secret": client_secret,
        })
        if not r.get("access_token"):
            raise RuntimeError("refresh_token 续期失败: %s" % r)
        self._save_token(r)
        return r

    def get_user_info(self) -> dict:
        """xpannasuinfo：返回授权用户信息（errno/uk/baidu_name/netdisk_name/vip_type/...）"""
        access_token = self._access_token()
        return self._request("GET", _URL_UINFO, params={
            "method": "uinfo", "openapi": "xpansdk", "access_token": access_token,
        })

    # ---- 路径处理（remote_path 相对沙箱根 /apps/{APP_NAME}，base_path 作子前缀）----

    def _full_path(self, remote_path: str) -> str:
        """API 实际路径 = /apps/{APP_NAME}[/base_path]/remote_path（沙箱内绝对路径）"""
        segs = [self.sandbox_root.strip("/")]  # apps/FileManager
        bp = (self.base_path or "").strip("/")
        if bp:
            segs.append(bp)
        rp = remote_path.strip("/")
        if rp:
            segs.append(rp)
        return "/" + "/".join(segs)

    # ---- 文件列表访问（xpanfilelist）----

    def _list_files(self, remote_dir: str) -> List[Dict[str, Any]]:
        access_token = self._access_token()
        dir_path = self._full_path(remote_dir)
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
