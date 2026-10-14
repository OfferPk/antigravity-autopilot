"""Configuration loading and validation for agy-autopilot."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("~/.config/agy-autopilot/config.toml").expanduser()
DEFAULT_DATA_DIR = Path("~/.local/share/agy-autopilot").expanduser()


@dataclass(frozen=True)
class ModelConfig:
    backend: str
    model: str = ""
    base_url: str = "http://127.0.0.1:11434/v1"
    model_path: str = ""


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    path: Path
    base_branch: str
    remote: str
    checks: tuple[tuple[str, ...], ...]
    check_timeout_seconds: int = 1800


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig
    projects: dict[str, ProjectConfig]
    branch_prefix: str = "antigravity"
    push: bool = True
    poll_seconds: int = 15
    config_path: Path = DEFAULT_CONFIG
    data_dir: Path = DEFAULT_DATA_DIR


def _expand(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.environ.get("AGY_AUTOPILOT_CONFIG", DEFAULT_CONFIG)).expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Config not found: {config_path}. Copy config.example.toml and set project/model values."
        )
    with config_path.open("rb") as handle:
        raw: dict[str, Any] = tomllib.load(handle)

    model_raw = raw.get("model", {})
    backend = str(model_raw.get("backend", "ollama")).lower()
    if backend not in {"ollama", "litert"}:
        raise ValueError("[model].backend must be 'ollama' or 'litert'.")
    model = ModelConfig(
        backend=backend,
        model=str(model_raw.get("name", "")),
        base_url=_expand(str(model_raw.get("base_url", "http://127.0.0.1:11434/v1"))),
        model_path=_expand(str(model_raw.get("model_path", ""))),
    )
    if backend == "ollama" and not model.model:
        raise ValueError("Set [model].name to a model already available in your local Ollama server.")
    if backend == "litert" and not model.model_path:
        raise ValueError("Set [model].model_path to the local .litertlm file.")

    automation = raw.get("automation", {})
    prefix = str(automation.get("branch_prefix", "antigravity")).strip("/ ")
    if not prefix or any(part in {".", ".."} for part in prefix.split("/")):
        raise ValueError("[automation].branch_prefix must be a safe non-empty branch prefix.")
    poll_seconds = int(automation.get("poll_seconds", 15))
    if not 1 <= poll_seconds <= 3600:
        raise ValueError("[automation].poll_seconds must be between 1 and 3600.")

    projects: dict[str, ProjectConfig] = {}
    for name, item in raw.get("projects", {}).items():
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Unsafe project name: {name!r}")
        project_path = Path(_expand(str(item.get("path", "")))).resolve()
        base_branch = str(item.get("base_branch", "")).strip()
        remote = str(item.get("remote", "origin")).strip()
        raw_checks = item.get("checks", [])
        if not project_path.is_absolute() or not base_branch or not remote:
            raise ValueError(f"Project {name!r} needs absolute path, base_branch, and remote.")
        if not isinstance(raw_checks, list) or any(
            not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command)
            for command in raw_checks
        ):
            raise ValueError(f"Project {name!r}: checks must be arrays of argument arrays, never shell strings.")
        timeout = int(item.get("check_timeout_seconds", 1800))
        if not 1 <= timeout <= 86400:
            raise ValueError(f"Project {name!r}: check_timeout_seconds must be 1..86400.")
        projects[name] = ProjectConfig(
            name=name,
            path=project_path,
            base_branch=base_branch,
            remote=remote,
            checks=tuple(tuple(command) for command in raw_checks),
            check_timeout_seconds=timeout,
        )
    if not projects:
        raise ValueError("Add at least one [projects.<name>] entry to the config.")

    data_dir = Path(_expand(str(automation.get("data_dir", DEFAULT_DATA_DIR)))).resolve()
    return AppConfig(
        model=model,
        projects=projects,
        branch_prefix=prefix,
        push=bool(automation.get("push", True)),
        poll_seconds=poll_seconds,
        config_path=config_path,
        data_dir=data_dir,
    )
