from typing import Protocol

from Network.Core import AENetReq, AENetRsp


class AEContextDelegate(Protocol):
    def send_request(self, request: AENetReq) -> None:
        ...

    def send_response(self, request: AENetReq, response: AENetRsp) -> None:
        ...
