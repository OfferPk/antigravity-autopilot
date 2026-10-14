from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agy_autopilot.config import ProjectConfig
from agy_autopilot.gitops import _run, commit_and_push, make_worktree, remove_worktree


class GitWorkflowTests(unittest.TestCase):
    def test_pushes_only_feature_branch_to_local_bare_remote(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            remote = base / "remote.git"
            repo = base / "repo"
            data_dir = base / "state"
            remote.mkdir()
            _run(["git", "init", "--bare", "-q", str(remote)], cwd=base)
            repo.mkdir()
            _run(["git", "init", "-q", str(repo)], cwd=base)
            _run(["git", "config", "user.email", "test@example.invalid"], cwd=repo)
            _run(["git", "config", "user.name", "Autopilot Test"], cwd=repo)
            (repo / "README.md").write_text("start\n", encoding="utf-8")
            _run(["git", "add", "README.md"], cwd=repo)
            _run(["git", "commit", "-m", "initial"], cwd=repo)
            _run(["git", "branch", "-M", "main"], cwd=repo)
            original_main = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            _run(["git", "remote", "add", "origin", str(remote)], cwd=repo)
            _run(["git", "push", "-u", "origin", "main"], cwd=repo)

            project = ProjectConfig("demo", repo, "main", "origin", ())
            task_id = "a" * 32
            worktree, branch = make_worktree(project, data_dir, task_id, "antigravity")
            (worktree / "README.md").write_text("start\nautomated change\n", encoding="utf-8")
            summary = commit_and_push(project, worktree, branch, task_id, push=True)

            pushed_ref = _run(["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"], cwd=base).stdout.strip()
            main_ref = _run(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"], cwd=base).stdout.strip()
            self.assertIn(branch, summary)
            self.assertNotEqual(pushed_ref, original_main)
            self.assertEqual(main_ref, original_main)
            remove_worktree(project, worktree)
            self.assertFalse(worktree.exists())


if __name__ == "__main__":
    unittest.main()
