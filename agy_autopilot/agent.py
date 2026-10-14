"""Create a workspace-scoped Antigravity SDK agent using a local model."""
from __future__ import annotations

from pathlib import Path


SYSTEM_INSTRUCTIONS = """You are a coding agent working only in the supplied isolated Git worktree. Implement the user's task carefully and make the smallest coherent change. You may inspect and edit files in this workspace, but do not publish, commit, change branches, access credentials, or attempt to read files outside the workspace. Do not invent secrets, API keys, or test results. Do not claim tests passed; the controller runs configured checks after you finish. Avoid unrelated refactors. At the end, summarize files changed and any limitations."""

_ALLOWED_TOOLS = [
    "list_directory", "search_directory", "find_file", "view_file",
    "create_file", "edit_file", "finish",
]


def _build_config(model_config, workspace: Path):
    try:
        from google.antigravity import CapabilitiesConfig, LiteRTAgentConfig, LocalOpenAIAgentConfig
        from google.antigravity.hooks.policy import allow, deny
        from google.antigravity.types import BuiltinTools
    except ImportError as exc:
        raise RuntimeError(
            "Antigravity SDK is not installed. Install this package in its virtual environment with `pip install -e .`."
        ) from exc

    capabilities = CapabilitiesConfig(
        enabled_tools=[getattr(BuiltinTools, {
            "list_directory": "LIST_DIR",
            "search_directory": "SEARCH_DIR",
            "find_file": "FIND_FILE",
            "view_file": "VIEW_FILE",
            "create_file": "CREATE_FILE",
            "edit_file": "EDIT_FILE",
            "finish": "FINISH",
        }[name]) for name in _ALLOWED_TOOLS]
    )
    policies = [deny("*"), *(allow(name) for name in _ALLOWED_TOOLS)]
    common = {
        "workspaces": [str(workspace)],
        "capabilities": capabilities,
        "policies": policies,
        "system_instructions": SYSTEM_INSTRUCTIONS,
    }
    if model_config.backend == "ollama":
        return LocalOpenAIAgentConfig(
            model=model_config.model,
            base_url=model_config.base_url,
            **common,
        ).lightweight()
    if model_config.backend == "litert":
        return LiteRTAgentConfig(
            model_path=model_config.model_path,
            **common,
        ).lightweight()
    raise ValueError(f"Unsupported local model backend: {model_config.backend}")


async def implement_task(model_config, workspace: Path, task: str) -> str:
    try:
        from google.antigravity import Agent
    except ImportError as exc:
        raise RuntimeError("Antigravity SDK is unavailable. Install `google-antigravity` in the venv.") from exc
    config = _build_config(model_config, workspace)
    prompt = (
        "Task for this project:\n\n" + task.strip() +
        "\n\nInspect the project first, implement the requested behavior, and update or add tests when appropriate. "
        "Do not run shell commands; the controller will run only the checks explicitly configured for this project."
    )
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        return await response.text()
