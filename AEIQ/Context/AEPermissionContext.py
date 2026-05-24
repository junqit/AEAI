import logging
from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext

logger = logging.getLogger(__name__)


class AEPermissionContext(AEBaseContext):

    async def on_request(self, request: AENetReq) -> None:
        logger.info(f"AEPermissionContext on_request: {request.model_dump_json(exclude_none=True)}")
