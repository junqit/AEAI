from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext


class AEWorkSpaceContext(AEBaseContext):
    paths = ["/ae/workspace"]

    def __init__(self, context_info: dict | None = None):
        super().__init__(ident="WorkSpace", context_info=context_info)

    async def handle_request(self, request: AENetReq, connection_id: str) -> None:
        pass
