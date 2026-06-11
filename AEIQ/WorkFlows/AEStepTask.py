from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid


class AETaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AETaskConfig:
    """任务初始化所需的结构体"""
    action: str
    level: int = 0
    payload: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class AETaskResult:
    """任务接收结果的数据结构"""
    task_id: str
    success: bool
    data: Any = None
    message: str = ""


@dataclass
class AETaskMessage:
    """任务自身的消息体，用于告知外部需要执行什么"""
    task_id: str
    level: int
    action: str
    payload: dict = field(default_factory=dict)
    description: str = ""


class AEStepTask:
    """
    单一步骤任务。
    提供接收处理结果的能力，并标识当前自己是否已经完成。
    """

    def __init__(self, config: AETaskConfig):
        self.task_id: str = f"task_{uuid.uuid4().hex[:8]}"
        self.action: str = config.action
        self.level: int = config.level
        self.payload: dict = config.payload
        self.description: str = config.description
        self.status: AETaskStatus = AETaskStatus.PENDING
        self.result: Optional[AETaskResult] = None

    @property
    def is_completed(self) -> bool:
        return self.status == AETaskStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == AETaskStatus.FAILED

    def receive_result(self, result: AETaskResult) -> bool:
        """
        接收外部处理结果，由任务自身判断是否完成。
        返回 True 表示任务已完成，False 表示未完成。
        """
        self.result = result
        if result.success:
            self.status = AETaskStatus.COMPLETED
        else:
            self.status = AETaskStatus.FAILED
        return self.is_completed

    def build_message(self) -> AETaskMessage:
        """组装自己的消息体，供外部获取当前任务的执行信息"""
        return AETaskMessage(
            task_id=self.task_id,
            level=self.level,
            action=self.action,
            payload=self.payload,
            description=self.description,
        )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "level": self.level,
            "payload": self.payload,
            "description": self.description,
            "status": self.status.value,
            "result": {
                "success": self.result.success,
                "data": self.result.data,
                "message": self.result.message,
            } if self.result else None,
        }
