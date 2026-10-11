"""
AEContextDelegate - Context 委托协议。

Context 通过本协议向外发送网络请求、网络回复与 LLM 请求。
任何实现以下方法的类即视为符合协议。
"""
from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from Network.Core import AENetReq, AENetRsp
    from .AELLMPayload import AELLMPayload


@runtime_checkable
class AENetworkDelegate(Protocol):
    """网络委托协议：仅包含网络请求与回复的发送。"""

    def send_request(self, request: 'AENetReq') -> None:
        """发送网络请求。"""
        ...

    def send_response(self, response: 'AENetRsp') -> None:
        """发送网络回复。"""
        ...


@runtime_checkable
class AEContextDelegate(AENetworkDelegate, Protocol):
    """Context 委托协议：在网络委托基础上增加 LLM 请求。"""

    def send_llm_request(self, payload: 'AELLMPayload') -> None:
        """发送 LLM 请求（无返回值；回复到达后经 dispatch 回流到对应 Context）。"""
        ...
