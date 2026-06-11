from typing import List, Optional
import logging

from .AEStepTask import AEStepTask, AETaskResult, AETaskMessage, AETaskStatus

logger = logging.getLogger(__name__)


class AEStepTaskManager:
    """
    步骤任务管理器。
    管理任务列表，接收外部处理结果并分发给对应任务，
    按 level 排序返回下一个待执行任务的信息。
    """

    def __init__(self):
        self._tasks: List[AEStepTask] = []

    def add_task(self, task: AEStepTask):
        self._tasks.append(task)

    def add_tasks(self, tasks: List[AEStepTask]):
        self._tasks.extend(tasks)

    @property
    def is_all_completed(self) -> bool:
        return all(t.is_completed or t.is_failed for t in self._tasks)

    def receive_result(self, result: AETaskResult) -> Optional[AETaskMessage]:
        """
        接收外部处理结果。
        根据 task_id 找到对应任务，将结果交给任务判断是否完成。
        返回下一个待执行任务的消息体，若全部完成则返回 None。
        """
        task = self._find_task(result.task_id)
        if task is None:
            logger.warning(f"Task not found: {result.task_id}")
            return None

        task.receive_result(result)
        logger.info(f"Task [{task.task_id}] status: {task.status.value}")

        return self.get_next_message()

    def get_next_message(self) -> Optional[AETaskMessage]:
        """按 level 排序，返回下一个待执行任务的消息体。如果有正在处理的任务则返回 None。"""
        has_in_progress = any(t.status == AETaskStatus.IN_PROGRESS for t in self._tasks)
        if has_in_progress:
            return None

        pending = [t for t in self._tasks if t.status == AETaskStatus.PENDING]
        if not pending:
            return None

        pending.sort(key=lambda t: t.level)
        next_task = pending[0]
        next_task.status = AETaskStatus.IN_PROGRESS

        return next_task.build_message()

    def get_all_tasks(self) -> List[dict]:
        """返回所有任务信息列表，按 level 排序"""
        sorted_tasks = sorted(self._tasks, key=lambda t: t.level)
        return [t.to_dict() for t in sorted_tasks]

    def get_status(self) -> dict:
        total = len(self._tasks)
        completed = sum(1 for t in self._tasks if t.is_completed)
        failed = sum(1 for t in self._tasks if t.is_failed)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": total - completed - failed,
            "is_all_completed": self.is_all_completed,
        }

    def _find_task(self, task_id: str) -> Optional[AEStepTask]:
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        return None
