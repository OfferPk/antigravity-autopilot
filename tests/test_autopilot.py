from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agy_autopilot.config import load_config
from agy_autopilot.gitops import _run, scan_staged_secrets
from agy_autopilot.queue import TaskQueue


class QueueTests(unittest.TestCase):
    def test_enqueue_claim_and_finish(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = TaskQueue(Path(temp))
            created = queue.enqueue("demo_app", "Add a health endpoint")
            claimed = queue.claim_next()
            self.assertEqual(created["id"], claimed["id"])
            self.assertEqual(claimed["status"], "running")
            self.assertIsNone(queue.claim_next())
            queue.finish(claimed, result="pushed branch")
            self.assertEqual(queue.status(), {"pending": 0, "running": 0, "done": 1, "failed": 0})

    def test_rejects_empty_or_oversized_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = TaskQueue(Path(temp))
            with self.assertRaises(ValueError):
                queue.enqueue("demo_app", "   ")
            with self.assertRaises(ValueError):
                queue.enqueue("demo_app", "x" * 12001)


class ConfigTests(unittest.TestCase):
    def test_loads_local_model_and_registered_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            config_path = root / "config.toml"
            config_path.write_text(
                f'''[model]\nbackend = "ollama"\nname = "coder-local"\n\n'''
                f'''[automation]\ndata_dir = "{root / 'state'}"\n\n'''
                f'''[projects.demo_app]\npath = "{project}"\nbase_branch = "main"\nremote = "origin"\nchecks = [["python", "-m", "unittest"]]\n''',
                encoding="utf-8",
            )
            config = load_config(config_path)
            self.assertEqual(config.model.backend, "ollama")
            self.assertEqual(config.projects["demo_app"].checks, (("python", "-m", "unittest"),))
            self.assertEqual(config.data_dir, root / "state")

    def test_rejects_shell_string_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            config_path = root / "config.toml"
            config_path.write_text(
                f'''[model]\nbackend = "ollama"\nname = "coder-local"\n'''
                f'''[projects.demo_app]\npath = "{project}"\nbase_branch = "main"\nchecks = ["pytest -q"]\n''',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_config(config_path)


class SecretScanTests(unittest.TestCase):
    def _repo(self, path: Path) -> None:
        path.mkdir()
        _run(["git", "init", "-q"], cwd=path)
        _run(["git", "config", "user.email", "test@example.invalid"], cwd=path)
        _run(["git", "config", "user.name", "Test"], cwd=path)

    def test_detects_new_token_in_staged_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            self._repo(repo)
            fake_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
            (repo / "app.py").write_text(f'TOKEN = "{fake_token}"\n', encoding="utf-8")
            _run(["git", "add", "app.py"], cwd=repo)
            findings = scan_staged_secrets(repo)
            self.assertTrue(any("GitHub token" in finding for finding in findings))

    def test_allows_env_example_name(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            self._repo(repo)
            (repo / ".env.example").write_text("API_KEY=your_key_here\n", encoding="utf-8")
            _run(["git", "add", ".env.example"], cwd=repo)
            findings = scan_staged_secrets(repo)
            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
