import os
import sys
from typing import Any, Dict, Optional, TYPE_CHECKING

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from AEIQConfig import config
from Network.Core import AENetReq, AENetRsp
from .AEPathValidator import AEPathValidator

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate


class AEBaseContext:
    paths: list = []

    def __init__(self, ident: str, context_info: Optional[dict] = None):
        self._context_info = context_info.copy() if context_info else {}
        self._context_info["ident"] = ident
        self.delegate: Optional['AEContextDelegate'] = None
        self.path_validator = AEPathValidator(config.get_path_whitelist())

    @property
    def ident(self) -> str:
        return self._context_info["ident"]

    @property
    def context_info(self) -> dict:
        return self._context_info

    def set_delegate(self, delegate: 'AEContextDelegate') -> None:
        self.delegate = delegate

    def send_response(self, connection_id: str, response: AENetRsp) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_response(connection_id, response)

    def matches_path(self, path: str) -> bool:
        if not path:
            return False
        for prefix in self.paths:
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    def resolve_operation(self, request: AENetReq) -> Optional[str]:
        if request.path:
            parts = request.path.strip("/").split("/")
            if len(parts) >= 3:
                return parts[2]
        return None

    async def handle_request(self, request: AENetReq, connection_id: str) -> None:
        raise NotImplementedError
