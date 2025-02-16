from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
from enum import Enum

class TaskStatus(Enum):
    in_queue = "in_queue"
    waiting_execution = "waiting_execution"
    executed = "executed"
    failed = "failed"

@dataclass
class Job:
    id: str
    command: str
    targets: List[str]     # List of session_ids
    created_at: datetime
    completed_at: Optional[datetime] = None
    task_statuses: Dict[str, TaskStatus] = field(default_factory=dict)  # {session_id: status}
    results: Dict[str, str] = field(default_factory=dict)  # {session_id: result}
    sent_to_sessions: List[str] = field(default_factory=list)  # List of sessions where command was sent

    def __post_init__(self):
        # Initialize task status for each target
        for target in self.targets:
            if target not in self.task_statuses:
                self.task_statuses[target] = TaskStatus.in_queue

    @property
    def status(self) -> TaskStatus:
        """Overall job status based on individual task statuses"""
        if all(status == TaskStatus.executed for status in self.task_statuses.values()):
            return TaskStatus.executed
        if all(status == TaskStatus.failed for status in self.task_statuses.values()):
            return TaskStatus.failed
        if any(status == TaskStatus.waiting_execution for status in self.task_statuses.values()):
            return TaskStatus.waiting_execution
        return TaskStatus.in_queue
