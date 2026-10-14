"""Queue worker: local Antigravity agent -> project checks -> guarded feature-branch push."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .agent import implement_task
from .config import AppConfig
from .gitops import commit_and_push, make_worktree, remove_worktree, run_checks
from .queue import TaskQueue


def process_one(config: AppConfig) -> bool:
    queue = TaskQueue(config.data_dir)
    task = queue.claim_next()
    if task is None:
        return False
    worktree: Path | None = None
    pushed = False
    try:
        project = config.projects.get(task["project"])
        if project is None:
            raise ValueError(f"Task references unconfigured project: {task['project']}")
        worktree, branch = make_worktree(project, config.data_dir, task["id"], config.branch_prefix)
        agent_summary = asyncio.run(implement_task(config.model, worktree, task["description"]))
        checks = run_checks(project, worktree)
        publish_summary = commit_and_push(
            project, worktree, branch, task["id"], push=config.push
        )
        pushed = config.push
        result = "\n".join([
            f"Project: {project.name}",
            f"Branch: {branch}",
            publish_summary,
            "Checks:\n" + ("\n\n".join(checks) if checks else "None configured."),
            "Agent summary:\n" + agent_summary,
        ])
        if config.push:
            try:
                remove_worktree(project, worktree)
            except Exception as cleanup_error:
                result += f"\nWarning: remote push succeeded, but local worktree cleanup failed: {cleanup_error}"
        else:
            result += f"\nLocal worktree retained at: {worktree}"
        queue.finish(task, result=result)
        print(f"Task {task['id'][:8]} completed: {publish_summary}", flush=True)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if worktree:
            detail += f"\nWorktree retained for inspection: {worktree}"
        if pushed:
            detail += "\nWARNING: remote push already succeeded; inspect the feature branch before retrying."
        queue.finish(task, error=detail)
        print(f"Task {task['id'][:8]} failed: {detail}", flush=True)
    return True


def run_worker(config: AppConfig, *, watch: bool = False) -> None:
    print(f"Autopilot worker ready; configured projects: {', '.join(config.projects)}", flush=True)
    try:
        while True:
            found = process_one(config)
            if not watch:
                return
            if not found:
                time.sleep(config.poll_seconds)
    except KeyboardInterrupt:
        print("Worker stopped.", flush=True)
