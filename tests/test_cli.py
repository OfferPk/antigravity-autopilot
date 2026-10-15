from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agy_autopilot import cli


class CliPresentationTests(unittest.TestCase):
    def setUp(self):
        self.status = {"pending": 2, "running": 1, "done": 4, "failed": 0}
        self.queue = Mock()
        self.queue.status.return_value = self.status
        self.config = SimpleNamespace(data_dir=Path(tempfile.gettempdir()), projects={})

    def _run_status(self, *arguments: str) -> str:
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["agy-autopilot", "status", *arguments]),
            patch.object(cli, "load_config", return_value=self.config),
            patch.object(cli, "TaskQueue", return_value=self.queue),
            contextlib.redirect_stdout(output),
        ):
            cli.main()
        return output.getvalue()

    def test_status_defaults_to_readable_summary(self):
        output = self._run_status()
        self.assertEqual(
            output,
            "Queue status\n"
            "  Pending      2\n"
            "  Running      1\n"
            "  Done         4\n"
            "  Failed       0\n"
            "  Total        7\n",
        )

    def test_status_json_mode_keeps_machine_readable_counts(self):
        output = self._run_status("--json")
        self.assertEqual(json.loads(output), self.status)

    def test_help_includes_examples_and_config_override(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["agy-autopilot", "--help"]), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                cli.main()
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Examples:", output.getvalue())
        self.assertIn("agy-autopilot status --json", output.getvalue())
        self.assertIn("AGY_AUTOPILOT_CONFIG", output.getvalue())

    def test_status_help_explains_json_option(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["agy-autopilot", "status", "--help"]), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                cli.main()
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Output counts as JSON for scripts", output.getvalue())


if __name__ == "__main__":
    unittest.main()
