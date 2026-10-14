"""MCP tools that enqueue work for the local Antigravity SDK worker."""
from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .queue import TaskQueue

mcp = FastMCP("Antigravity Local Autopilot")


def _config():
    return load_config(os.environ.get("AGY_AUTOPILOT_CONFIG"))


@mcp.tool()
def list_projects() -> list[dict[str, str]]:
    """List the local Git projects explicitly registered by the owner."""
    config = _config()
    return [
        {"name": project.name, "path": str(project.path), "base_branch": project.base_branch}
        for project in config.projects.values()
    ]


@mcp.tool()
def submit_coding_task(project: str, task: str) -> dict[str, str]:
    """Queue a coding request for an allowlisted project; the local worker will use a local model, test it, then push a feature branch."""
    config = _config()
    if project not in config.projects:
        raise ValueError(f"Unknown project {project!r}. Use list_projects to see configured project names.")
    queued = TaskQueue(config.data_dir).enqueue(project, task)
    return {"task_id": queued["id"], "project": project, "status": "pending"}


@mcp.tool()
def queue_status() -> dict[str, int]:
    """Show counts of queued, running, completed, and failed local tasks."""
    config = _config()
    return TaskQueue(config.data_dir).status()


@mcp.tool()
def get_task(task_id: str) -> dict[str, str]:
    """Read the result/error record for a task by its 32-character task id."""
    if len(task_id) != 32 or any(c not in "0123456789abcdef" for c in task_id):
        raise ValueError("task_id must be the 32-character id returned by submit_coding_task.")
    config = _config()
    queue = TaskQueue(config.data_dir)
    for folder in (queue.pending, queue.running, queue.done, queue.failed):
        path = folder / f"{task_id}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return {key: str(value) for key, value in data.items()}
    raise FileNotFoundError(f"No task found: {task_id}")


def main() -> None:
    # The MCP server is local stdio only; it does not open a network listener.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
