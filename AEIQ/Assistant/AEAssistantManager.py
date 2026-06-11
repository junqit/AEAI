from typing import Dict, Optional
import logging

from .AEExpertAssistant import AEExpertAssistant

logger = logging.getLogger(__name__)


class AEAssistantManager:

    def __init__(self):
        # task_id -> AEExpertAssistant
        self._assistants: Dict[str, AEExpertAssistant] = {}
        logger.info("AEAssistantManager initialized")

    def create(self, user_question: str) -> AEExpertAssistant:
        assistant = AEExpertAssistant()
        self._assistants[assistant.task_id] = assistant
        assistant.start(user_question)
        logger.info(f"Assistant created: {assistant.task_id}")
        return assistant

    def get(self, task_id: str) -> Optional[AEExpertAssistant]:
        return self._assistants.get(task_id)

    def destroy(self, task_id: str) -> bool:
        assistant = self._assistants.pop(task_id, None)
        if assistant is None:
            logger.warning(f"Assistant not found: {task_id}")
            return False
        logger.info(f"Assistant destroyed: {task_id}")
        return True

    def destroy_all(self) -> int:
        count = len(self._assistants)
        self._assistants.clear()
        logger.info(f"All assistants destroyed, count={count}")
        return count

    def list_all(self) -> list:
        return [assistant.get_status() for assistant in self._assistants.values()]

    @property
    def count(self) -> int:
        return len(self._assistants)
