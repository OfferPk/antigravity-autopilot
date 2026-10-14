"""Git worktree, verification, secret scanning, and branch publishing."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .config import ProjectConfig


class GitError(RuntimeError):
    pass


_SECRET_PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("OpenAI-style secret key", re.compile(r"\bsk-[A-Za-z0-9]{24,}\b")),
]
_SENSITIVE_PATH = re.compile(
    r"(^|/)(\.env(?:\..*)?|id_(?:rsa|ed25519)|credentials\.(?:json|toml)|secrets?\.(?:json|ya?ml))$",
    re.IGNORECASE,
)
_PLACEHOLDERS = ("your_", "replace_me", "changeme", "example", "placeholder", "<", "${")


def _run(command: list[str], *, cwd: Path, timeout: int = 1200, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()[-6000:]
        raise GitError(f"Command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result


def make_worktree(project: ProjectConfig, data_dir: Path, task_id: str, branch_prefix: str) -> tuple[Path, str]:
    root = project.path
    if not (root / ".git").exists() and not (root / ".git").is_file():
        raise GitError(f"Not a Git repository: {root}")
    _run(["git", "fetch", "--no-tags", project.remote, project.base_branch], cwd=root)
    branch = f"{branch_prefix}/{task_id[:8]}"
    worktree = data_dir / "worktrees" / task_id
    worktree.parent.mkdir(parents=True, exist_ok=True)
    if worktree.exists():
        raise GitError(f"Refusing to overwrite existing worktree path: {worktree}")
    _run(["git", "worktree", "add", "-b", branch, str(worktree), "FETCH_HEAD"], cwd=root)
    return worktree, branch


def run_checks(project: ProjectConfig, worktree: Path) -> list[str]:
    if not project.checks:
        return ["No checks configured; tests were not run."]
    output: list[str] = []
    for command in project.checks:
        result = subprocess.run(
            list(command), cwd=worktree, text=True, capture_output=True,
            timeout=project.check_timeout_seconds, env={**os.environ, "CI": "1"},
        )
        output.append(f"$ {' '.join(command)}\n{(result.stdout + result.stderr)[-10000:]}")
        if result.returncode:
            raise GitError(f"Project check failed ({result.returncode}): {' '.join(command)}\n{output[-1][-6000:]}")
    return output


def scan_staged_secrets(worktree: Path) -> list[str]:
    names = _run(["git", "diff", "--cached", "--name-only", "-z"], cwd=worktree).stdout.split("\0")
    findings: list[str] = []
    for name in filter(None, names):
        if _SENSITIVE_PATH.search(name) and not name.lower().endswith((".example", ".template", ".sample")):
            findings.append(f"Sensitive filename staged: {name}")
    patch = _run(["git", "diff", "--cached", "--no-ext-diff", "--unified=0"], cwd=worktree).stdout
    for line_no, line in enumerate(patch.splitlines(), start=1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        for label, pattern in _SECRET_PATTERNS:
            if pattern.search(added):
                findings.append(f"Possible {label} on staged diff line {line_no}")
        low = added.lower()
        if re.search(r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\b\s*[:=]\s*['\"]?[^\s'\"]{16,}", added):
            if not any(marker in low for marker in _PLACEHOLDERS):
                findings.append(f"Possible hard-coded credential on staged diff line {line_no}")
    return findings


def commit_and_push(project: ProjectConfig, worktree: Path, branch: str, task_id: str, *, push: bool) -> str:
    _run(["git", "add", "--all"], cwd=worktree)
    _run(["git", "diff", "--cached", "--check"], cwd=worktree)
    if not _run(["git", "diff", "--cached", "--quiet"], cwd=worktree, check=False).returncode:
        raise GitError("Agent produced no changes; nothing was committed or pushed.")
    findings = scan_staged_secrets(worktree)
    if findings:
        raise GitError("Secret scan blocked publishing:\n- " + "\n- ".join(findings))
    _run(["git", "-c", "commit.gpgsign=false", "commit", "-m", f"chore(autopilot): task {task_id[:8]}"], cwd=worktree)
    commit = _run(["git", "rev-parse", "--short", "HEAD"], cwd=worktree).stdout.strip()
    if push:
        _run(["git", "push", "--set-upstream", project.remote, f"HEAD:refs/heads/{branch}"], cwd=worktree)
        return f"Committed {commit} and pushed branch {branch} to {project.remote}. Default branch was not changed."
    return f"Committed {commit} locally on branch {branch}; push was disabled in configuration."


def remove_worktree(project: ProjectConfig, worktree: Path) -> None:
    if worktree.exists():
        _run(["git", "worktree", "remove", "--force", str(worktree)], cwd=project.path)
