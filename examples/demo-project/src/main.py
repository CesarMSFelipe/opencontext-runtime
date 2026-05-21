"""Entry point for the demo project."""

from __future__ import annotations

from auth import AuthService
from services import TaskService, UserDashboardService


def main() -> None:
    """Main entry point."""
    auth = AuthService()
    tasks = TaskService()
    dashboard = UserDashboardService(auth, tasks)

    # Register a user
    user = auth.register("alice", "alice@example.com", "secret123")
    print(f"Registered: {user.username}")

    # Authenticate
    token = auth.authenticate("alice", "secret123")
    print(f"Token: {token[:20]}...")

    # Create a project
    project = tasks.create_project("Demo Project", "A sample project")
    print(f"Project: {project.name}")

    # Add tasks
    tasks.create_task(project.id, "Setup environment", priority="high")
    tasks.create_task(project.id, "Write tests", priority="medium")
    tasks.create_task(project.id, "Deploy to production", priority="low")

    # Show stats
    stats = dashboard.get_user_stats(token)
    print(f"User: {stats}")

    # Show projects
    projects = dashboard.get_user_projects(token)
    print(f"Projects: {len(projects)}")


if __name__ == "__main__":
    main()
