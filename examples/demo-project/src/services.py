"""Business logic services for the demo project."""

from __future__ import annotations

from typing import Any

from auth import AuthService
from models import Project, Task


class TaskService:
    """Service for task management."""

    def __init__(self) -> None:
        self._projects: dict[int, Project] = {}
        self._next_project_id = 1

    def create_project(self, name: str, description: str = "") -> Project:
        """Create a new project."""
        project = Project(
            id=self._next_project_id,
            name=name,
            description=description,
        )
        self._projects[project.id] = project
        self._next_project_id += 1
        return project

    def get_project(self, project_id: int) -> Project | None:
        """Get a project by ID."""
        return self._projects.get(project_id)

    def create_task(
        self,
        project_id: int,
        title: str,
        description: str = "",
        priority: str = "medium",
    ) -> Task | None:
        """Create a new task in a project."""
        project = self.get_project(project_id)
        if project is None:
            return None

        task = Task(
            id=0,
            title=title,
            description=description,
            priority=priority,
        )
        return project.add_task(task)

    def update_task_status(
        self,
        project_id: int,
        task_id: int,
        status: str,
    ) -> bool:
        """Update the status of a task."""
        project = self.get_project(project_id)
        if project is None:
            return False

        for task in project.tasks:
            if task.id == task_id:
                task.status = status
                return True
        return False


class UserDashboardService:
    """Service for user dashboard data."""

    def __init__(self, auth_service: AuthService, task_service: TaskService) -> None:
        self._auth = auth_service
        self._tasks = task_service

    def get_user_stats(self, token: str) -> dict[str, Any] | None:
        """Get statistics for the authenticated user."""
        user = self._auth.validate_token(token)
        if user is None:
            return None

        return {
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
        }

    def get_user_projects(self, token: str) -> list[dict[str, Any]]:
        """Get all projects for the authenticated user."""
        user = self._auth.validate_token(token)
        if user is None:
            return []

        return [
            {
                "id": p.id,
                "name": p.name,
                "task_count": len(p.tasks),
            }
            for p in self._tasks._projects.values()
        ]
