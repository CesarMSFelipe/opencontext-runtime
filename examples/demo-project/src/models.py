"""Data models for the demo project."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Task:
    """A task in the system."""

    id: int
    title: str
    description: str = ""
    status: str = "pending"  # pending, in_progress, completed
    priority: str = "medium"  # low, medium, high
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    owner_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "owner_id": self.owner_id,
        }


@dataclass
class Project:
    """A project containing tasks."""

    id: int
    name: str
    description: str = ""
    tasks: list[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def add_task(self, task: Task) -> Task:
        """Add a task to the project."""
        task.id = len(self.tasks) + 1
        self.tasks.append(task)
        return task

    def get_tasks_by_status(self, status: str) -> list[Task]:
        """Get all tasks with a given status."""
        return [t for t in self.tasks if t.status == status]

    def get_tasks_by_priority(self, priority: str) -> list[Task]:
        """Get all tasks with a given priority."""
        return [t for t in self.tasks if t.priority == priority]
