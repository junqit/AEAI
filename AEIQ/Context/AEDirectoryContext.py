import os
from typing import Any, Dict

from Network.Core import AENetReq, AENetRsp
from .AEBaseContext import AEBaseContext


class AEDirectoryContext(AEBaseContext):

    paths = ["/ae/context/home"]

    def __init__(self, context_info: dict | None = None):
        super().__init__(ident="Directory", context_info=context_info)

    async def handle_request(self, request: AENetReq, connection_id: str) -> None:
        result = {"home": os.path.expanduser("~")}
        response = AENetRsp.create_success(requestId=request.requestId, result=result)
        self.send_response(connection_id, response)
