import logging
from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)


class AEPermissionContext(AEBaseContext):

    def __init__(self, space: str = ""):
        super().__init__(context_type=AEContextType.permission, space=space)

    async def on_request(self, request: AENetReq) -> None:
        pass
