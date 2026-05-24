import logging
from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext

logger = logging.getLogger(__name__)


class AEWorkSpaceContext(AEBaseContext):

    async def on_request(self, request: AENetReq) -> None:
        logger.info(f"AEWorkSpaceContext on_request: {request.model_dump_json(exclude_none=True)}")
