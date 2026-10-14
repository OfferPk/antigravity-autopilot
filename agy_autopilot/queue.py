"""Small filesystem task queue shared by the MCP server and worker."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TaskQueue:
    def __init__(self, data_dir: Path):
        self.root = data_dir / "queue"
        self.pending = self.root / "pending"
        self.running = self.root / "running"
        self.done = self.root / "done"
        self.failed = self.root / "failed"
        for directory in (self.pending, self.running, self.done, self.failed):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def enqueue(self, project: str, description: str) -> dict[str, Any]:
        description = description.strip()
        if not description:
            raise ValueError("Task description cannot be empty.")
        if len(description) > 12000:
            raise ValueError("Task description must be 12,000 characters or fewer.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project):
            raise ValueError("Project must be the name of a configured project.")
        task = {
            "id": uuid.uuid4().hex,
            "project": project,
            "description": description,
            "created_at": self._now(),
            "status": "pending",
        }
        target = self.pending / f"{task['id']}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, target)
        return task

    def claim_next(self) -> dict[str, Any] | None:
        for source in sorted(self.pending.glob("*.json"), key=lambda p: p.name):
            destination = self.running / source.name
            try:
                os.replace(source, destination)
            except FileNotFoundError:
                continue
            task = json.loads(destination.read_text(encoding="utf-8"))
            task["status"] = "running"
            task["started_at"] = self._now()
            destination.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return task
        return None

    def finish(self, task: dict[str, Any], *, error: str | None = None, result: str = "") -> None:
        task_id = str(task["id"])
        if not re.fullmatch(r"[a-f0-9]{32}", task_id):
            raise ValueError("Invalid task id.")
        task["status"] = "failed" if error else "done"
        task["finished_at"] = self._now()
        if result:
            task["result"] = result[-12000:]
        if error:
            task["error"] = error[-12000:]
        source = self.running / f"{task_id}.json"
        target_dir = self.failed if error else self.done
        temp = target_dir / f"{task_id}.tmp"
        temp.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, target_dir / f"{task_id}.json")
        source.unlink(missing_ok=True)

    def status(self) -> dict[str, Any]:
        return {
            "pending": len(list(self.pending.glob("*.json"))),
            "running": len(list(self.running.glob("*.json"))),
            "done": len(list(self.done.glob("*.json"))),
            "failed": len(list(self.failed.glob("*.json"))),
        }
