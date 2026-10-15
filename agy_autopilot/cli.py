"""Command-line interface for agy-autopilot."""
from __future__ import annotations

import argparse
import json
import os

from .config import load_config
from .queue import TaskQueue


def _format_status(status: dict[str, int]) -> str:
    labels = (
        ("pending", "Pending"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
    )
    lines = ["Queue status"]
    lines.extend(f"  {label:<8} {status[key]:>5}" for key, label in labels)
    lines.append(f"  {'Total':<8} {sum(status[key] for key, _ in labels):>5}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agy-autopilot",
        description="Local-first coding queue for registered projects.",
        epilog=(
            "Examples:\n"
            '  agy-autopilot enqueue --project my_app "Add a settings page"\n'
            "  agy-autopilot status\n"
            "  agy-autopilot status --json\n"
            "  agy-autopilot worker --watch\n\n"
            "Configuration: AGY_AUTOPILOT_CONFIG overrides "
            "~/.config/agy-autopilot/config.toml."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    enqueue = sub.add_parser("enqueue", help="Add a coding task to a registered project queue")
    enqueue.add_argument("--project", required=True, help="Configured project name")
    enqueue.add_argument("task", help="Task description")

    status = sub.add_parser("status", help="Show pending, running, done, and failed task counts")
    status.add_argument("--json", action="store_true", help="Output counts as JSON for scripts")

    worker = sub.add_parser("worker", help="Run one queue pass or keep processing tasks")
    worker.add_argument("--watch", action="store_true", help="Keep polling the queue")

    sub.add_parser("mcp", help="Run the local stdio MCP server for queue operations")
    args = parser.parse_args()

    if args.command == "mcp":
        from .mcp_server import main as run_mcp
        run_mcp()
        return

    config = load_config(os.environ.get("AGY_AUTOPILOT_CONFIG"))
    queue = TaskQueue(config.data_dir)
    if args.command == "enqueue":
        if args.project not in config.projects:
            parser.error(f"Unknown project {args.project!r}; configured projects: {', '.join(config.projects)}")
        task = queue.enqueue(args.project, args.task)
        print(json.dumps({"task_id": task["id"], "project": args.project, "status": "pending"}, indent=2))
    elif args.command == "status":
        status = queue.status()
        print(json.dumps(status, indent=2) if args.json else _format_status(status))
    elif args.command == "worker":
        from .worker import run_worker
        run_worker(config, watch=args.watch)
