"""
AE Baidu Credential - 百度网盘认证信息与 OAuth 能力。

集中承载一切与 Credential 相关的能力与参数：
  - 参数（__init__ 仅 4 个）：app_name / app_key / app_secret / credential_path。
    credential_path 为 token 缓存文件路径；__init__ 内部从其加载 token，4 个参数即可完整内部逻辑。
  - 能力：is_valid / has_refresh_token（判断）、save（持久化）、refresh（refresh_token 续期）、
    authorize（device-code 授权）、authorize_with_code（authorization-code 授权）、
    get_access_token（取有效 token，过期自动 refresh）。
授权/刷新走 openapi.baidu.com，发网络请求；其余读取/判断不发网络（token 由 credential_path 加载）。

结构（非平铺）：BDToken（token 状态值对象）+ AEBDCredential（4 参数 + OAuth 能力）。
"""
import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

# ---- OAuth 端点（openapi.baidu.com）----
_OPENAPI_HOST = "https://openapi.baidu.com"
_URL_DEVICE_CODE = _OPENAPI_HOST + "/oauth/2.0/device/code"   # ?response_type=device_code&openapi=xpansdk
_URL_TOKEN = _OPENAPI_HOST + "/oauth/2.0/token"              # ?grant_type=<device_token|authorization_code|refresh_token>&openapi=xpansdk

_DEFAULT_SCOPE = "basic,netdisk"
# token 提前续期余量（秒）：距过期不足此值即视为无效，避免边界过期
_REFRESH_MARGIN = 60


@dataclass
class BDToken:
    """OAuth token 状态值对象（来自 device_token/refresh_token/auth_code 响应或缓存）"""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: int = 0          # unix 秒；0 表示未知（保守视为未过期）
    scope: Optional[str] = None

    @property
    def is_present(self) -> bool:
        return bool(self.access_token)

    def is_expired(self, margin: int = _REFRESH_MARGIN) -> bool:
        if not self.expires_at:
            return False  # 未知过期时间，由调用方在网络调用时兜底
        return self.expires_at - margin <= int(time.time())

    @classmethod
    def from_response(cls, resp: dict, prev: "BDToken" = None) -> "BDToken":
        """从 OAuth 响应构造；refresh_token 缺省时沿用 prev（refresh 响应可能不含）"""
        access_token = resp.get("access_token")
        if not access_token:
            raise ValueError("OAuth 响应缺少 access_token: %s" % resp)
        expires_in = resp.get("expires_in")
        refresh_token = resp.get("refresh_token") or (prev.refresh_token if prev else None)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=int(time.time()) + int(expires_in) if expires_in else 0,
            scope=resp.get("scope"),
        )

    @classmethod
    def from_cache(cls, data: dict) -> "BDToken":
        if not data:
            return cls()
        return cls(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            expires_at=int(data.get("expires_at") or 0),
            scope=data.get("scope"),
        )

    def to_cache(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }


class AEBDCredential:
    """百度网盘认证信息 + OAuth 能力。__init__ 仅 4 参数即可完整内部逻辑。"""

    def __init__(self, app_name: str, app_key: Optional[str], app_secret: Optional[str], credential_path: str):
        self._app_name = app_name
        self._app_key = app_key
        self._app_secret = app_secret
        self._credential_path = credential_path
        self._token: BDToken = self._read_token_cache(credential_path)
        self.delegate = None  # 创建方回调：on_valid(cred) / on_refreshed(cred)

    # ---- 内部：从缓存加载 token ----

    @staticmethod
    def _read_token_cache(credential_path: str) -> BDToken:
        try:
            with open(credential_path, "r", encoding="utf-8") as f:
                return BDToken.from_cache(json.load(f))
        except (OSError, ValueError):
            return BDToken()

    # ---- HTTP（OAuth GET 专用）----

    @staticmethod
    def _http_get(url: str, params=None, timeout: int = 30) -> dict:
        resp = requests.get(url, params=params, timeout=timeout)
        try:
            return resp.json()
        except ValueError:
            raise RuntimeError(
                "百度 OpenAPI 非 JSON 响应 status=%s body=%s"
                % (resp.status_code, resp.text[:200]))

    # ---- 有效性 ----

    def is_valid(self) -> bool:
        """当前 token 是否可用：存在且未过期（含提前续期余量）"""
        return self._token.is_present and not self._token.is_expired()

    def has_refresh_token(self) -> bool:
        return bool(self._token.refresh_token)

    # ---- 持久化（用 OAuth 响应更新内存与缓存文件）----

    def save(self, response: dict) -> BDToken:
        """用 OAuth 响应更新 token 并落盘缓存（权限 0600）"""
        self._token = BDToken.from_response(response, prev=self._token)
        try:
            os.makedirs(os.path.dirname(self._credential_path) or ".", exist_ok=True)
            with open(self._credential_path, "w", encoding="utf-8") as f:
                json.dump(self._token.to_cache(), f, ensure_ascii=False, indent=2)
                f.flush()
            os.chmod(self._credential_path, 0o600)
        except OSError:
            pass  # 落盘失败不阻断内存中的 token
        return self._token

    # ---- OAuth 能力：刷新 ----

    def refresh(self) -> BDToken:
        """用 refresh_token 续期 access_token；成功更新内存与缓存。发网络请求。"""
        if not (self._app_key and self._app_secret and self._token.refresh_token):
            raise RuntimeError("refresh_token 续期缺参数（client_id/client_secret/refresh_token）")
        r = self._http_get(_URL_TOKEN, params={
            "grant_type": "refresh_token", "openapi": "xpansdk",
            "refresh_token": self._token.refresh_token,
            "client_id": self._app_key, "client_secret": self._app_secret,
        })
        if not r.get("access_token"):
            raise RuntimeError("refresh_token 续期失败: %s" % r)
        token = self.save(r)
        self._notify_refreshed()
        return token

    # ---- OAuth 能力：授权 ----

    def authorize(self, scope: str = _DEFAULT_SCOPE, timeout: int = 600) -> BDToken:
        """device-code OAuth 授权（交互式，首次使用调用一次）。

        流程：取 device_code → 打印 verification_url/qrcode_url + user_code →
        轮询 device_token 端点，用户完成授权后拿到 access_token/refresh_token → 缓存。
        """
        if not (self._app_key and self._app_secret):
            raise RuntimeError("缺少 client_id/client_secret")
        d = self._http_get(_URL_DEVICE_CODE, params={
            "response_type": "device_code", "openapi": "xpansdk",
            "client_id": self._app_key, "scope": scope,
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
        deadline = int(time.time()) + min(expires_in, timeout)
        while int(time.time()) < deadline:
            r = self._http_get(_URL_TOKEN, params={
                "grant_type": "device_token", "openapi": "xpansdk",
                "code": device_code, "client_id": self._app_key, "client_secret": self._app_secret,
            })
            if r.get("access_token"):
                print("[百度网盘授权] 成功，token 已缓存到 %s" % self._credential_path)
                token = self.save(r)
                self._notify_valid()
                return token
            # 用户尚未授权：按 interval 重试；遇 fatal 错误（过期/拒绝）立即终止
            err = str(r.get("error") or r.get("errmsg") or "")
            if err and ("expired" in err or "denied" in err):
                raise RuntimeError("device-code 授权失败: %s" % r)
            time.sleep(interval)
        raise RuntimeError("device-code 授权超时，未在 %ss 内完成授权" % timeout)

    def authorize_with_code(self, code: str, redirect_uri: str = "oob") -> BDToken:
        """authorization-code OAuth 授权（备选：用浏览器回调/粘贴的 code 换 token）"""
        if not (self._app_key and self._app_secret):
            raise RuntimeError("缺少 client_id/client_secret")
        r = self._http_get(_URL_TOKEN, params={
            "grant_type": "authorization_code", "openapi": "xpansdk",
            "code": code, "client_id": self._app_key, "client_secret": self._app_secret,
            "redirect_uri": redirect_uri,
        })
        if not r.get("access_token"):
            raise RuntimeError("authorization_code 换 token 失败: %s" % r)
        token = self.save(r)
        self._notify_valid()
        return token

    # ---- 取有效 token（过期自动 refresh）----

    def get_access_token(self) -> str:
        """返回有效 access_token；过期则自动 refresh，失败抛错指引 authorize()"""
        if self.is_valid():
            return self._token.access_token
        if self.has_refresh_token():
            self.refresh()
            if self.is_valid():
                return self._token.access_token
        raise RuntimeError("百度网盘未授权或 token 已失效，请先调用 authorize() 完成授权")

    # ---- 验证 + delegate 回调 ----

    def verify(self) -> bool:
        """验证有效；过期则刷新。成功回调 delegate（on_valid 或 on_refreshed）"""
        if self.is_valid():
            self._notify_valid()
            return True
        if self.has_refresh_token():
            try:
                self.refresh()  # 成功时回调 on_refreshed
            except RuntimeError:
                return False
            return self.is_valid()
        return False

    def _notify_valid(self):
        """回调创建方：验证有效（credential 完成）"""
        if self.delegate is not None:
            self.delegate.on_valid(self)

    def _notify_refreshed(self):
        """回调创建方：刷新成功（credential 完成）"""
        if self.delegate is not None:
            self.delegate.on_refreshed(self)

    # ---- 访问器 ----

    @property
    def app_name(self) -> str:
        return self._app_name

    @property
    def app_key(self) -> Optional[str]:
        return self._app_key

    @property
    def app_secret(self) -> Optional[str]:
        return self._app_secret

    @property
    def credential_path(self) -> str:
        return self._credential_path

    @property
    def access_token(self) -> Optional[str]:
        return self._token.access_token

    @property
    def refresh_token(self) -> Optional[str]:
        return self._token.refresh_token

    @property
    def token(self) -> BDToken:
        return self._token
