from typing import Protocol, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp

if TYPE_CHECKING:
    from .AELLMPayload import AELLMPayload


class AEContextDelegate(Protocol):
    def send_request(self, request: AENetReq) -> None:
        ...

    def send_response(self, response: AENetRsp) -> None:
        ...

    async def send_llm_request(self, payload: 'AELLMPayload') -> str:
        ...
