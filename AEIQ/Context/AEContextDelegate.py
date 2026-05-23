from typing import Protocol

from Network.Core import AENetReq


class AEContextDelegate(Protocol):
    def send_request(self, request: AENetReq) -> None:
        ...
