import logging
from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext

logger = logging.getLogger(__name__)


class AEDirectoryContext(AEBaseContext):

    async def on_request(self, request: AENetReq) -> None:
        logger.info(f"AEDirectoryContext on_request: {request.model_dump_json(exclude_none=True)}")
