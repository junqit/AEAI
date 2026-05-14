from typing import Optional, Protocol, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp

if TYPE_CHECKING:
    from .AEBaseContext import AEBaseContext


class AEContextDelegate(Protocol):
    def send_response(self, connection_id: str, response: AENetRsp) -> None:
        ...

    def register_context(self, context: 'AEBaseContext') -> None:
        ...

    def unregister_context(self, ident: str) -> None:
        ...
