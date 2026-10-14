"""Command-line interface for agy-autopilot."""
from __future__ import annotations

import argparse
import json
import os

from .config import load_config
from .queue import TaskQueue


def main() -> None:
    parser = argparse.ArgumentParser(prog="agy-autopilot", description="Local Antigravity SDK coding automation")
    sub = parser.add_subparsers(dest="command", required=True)

    enqueue = sub.add_parser("enqueue", help="Queue a coding task for a registered project")
    enqueue.add_argument("--project", required=True)
    enqueue.add_argument("task", help="Task text")

    sub.add_parser("status", help="Show queue counts")

    worker = sub.add_parser("worker", help="Process queued tasks")
    worker.add_argument("--watch", action="store_true", help="Keep polling the queue")

    sub.add_parser("mcp", help="Run the local stdio MCP queue server")
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
        print(json.dumps(queue.status(), indent=2))
    elif args.command == "worker":
        from .worker import run_worker
        run_worker(config, watch=args.watch)
