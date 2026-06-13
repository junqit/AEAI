import logging
from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)


class AEPermissionContext(AEBaseContext):

    def __init__(self, user=None, space: str = ""):
        super().__init__(context_type=AEContextType.permission, user=user, space=space)

    async def on_request(self, request: AENetReq) -> None:
        logger.info(f"AEPermissionContext on_request: {request.model_dump_json(exclude_none=True)}")
