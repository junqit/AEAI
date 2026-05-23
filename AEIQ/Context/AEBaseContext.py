from typing import Optional, TYPE_CHECKING

from Network.Core import AENetReq

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate


class AEBaseContext:

    def __init__(self):
        self.delegate: Optional['AEContextDelegate'] = None

    def set_delegate(self, delegate: 'AEContextDelegate') -> None:
        self.delegate = delegate

    def send_request(self, request: AENetReq) -> None:
        """通过 delegate 把需要发送的 NetReq 传给 AEContextManager"""
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_request(request)

    async def handle_request(self, request: AENetReq) -> None:
        raise NotImplementedError
