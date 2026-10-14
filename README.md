# Antigravity Local Autopilot

A reusable, local-first coding queue for projects you own. It uses the **official Google Antigravity Python SDK** with a local model (Ollama/LM Studio/vLLM or LiteRT), plus a small stdio MCP server for queuing work from Antigravity. It does **not** reverse-engineer private endpoints, scrape hidden source code, or require a Gemini/API key for local inference.

## What it does

1. Registers only the project directories you list in `config.toml`.
2. Accepts a coding task from the CLI or the `submit_coding_task` MCP tool.
3. Fetches the selected repo's configured base branch and makes an isolated Git worktree on `antigravity/<task-id>`.
4. Runs the local Antigravity SDK agent with file tools limited to that worktree; shell, web, credentials, commit, and push tools are not exposed to the model.
5. Runs only the test/check argument arrays you explicitly configured, then checks the staged diff for common secrets.
6. If checks pass, commits and pushes the **feature branch** using Git's existing credential helper. It never pushes directly to the default branch or merges a PR.

Tasks are not invented: enqueue a task for each feature/bug or integrate your own trusted task feed. Keep `agy-autopilot worker --watch` running to process the queue continuously.

## Keyless model options

- **Ollama (recommended starter):** run a compatible coding model locally, for example `ollama pull qwen2.5-coder:14b`, and configure its local OpenAI-compatible URL. No API key is sent. Model quality and speed depend on your machine/model.
- **LiteRT:** use the Antigravity SDK's `LiteRTAgentConfig` and a local `.litertlm` checkpoint. Google's current docs recommend at least 24 GB VRAM/unified memory for Gemma 4 26B A4B; model import is a large download and CPU-only inference may be slow. This project does not download a model automatically.

Local model inference avoids a cloud API key, but GitHub still needs a one-time account login/credential-helper setup to authorize `git push`. Do not put a GitHub token in this project's config. If `git push` is not authenticated, the task fails and leaves its worktree/branch for inspection.

## Install

Python 3.11+, Git, and an already working local Ollama/compatible server or LiteRT model are required.

```bash
cd /path/to/antigravity-autopilot
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For Ollama, install/run Ollama separately and pull a local coding model; choose a model compatible with your available RAM/VRAM. For LiteRT, follow Google's [local models guide](https://antigravity.google/docs/sdk/local-models/).

## Configure any number of projects

Copy `config.example.toml` to `~/.config/agy-autopilot/config.toml` and edit it. Each `[projects.<name>]` entry must point to an existing Git repository, name its base branch and remote, and list checks as argument arrays (not shell strings):

```toml
[model]
backend = "ollama"
name = "qwen2.5-coder:14b"
base_url = "http://127.0.0.1:11434/v1"

[automation]
branch_prefix = "antigravity"
push = true
poll_seconds = 15

[projects.my_app]
path = "/absolute/path/to/my-app"
base_branch = "main"
remote = "origin"
checks = [["npm", "test", "--", "--runInBand"], ["npm", "run", "lint"]]
check_timeout_seconds = 1800
```

Add one project block for each project. Commands in `checks` are executed by the controller (not by the model) with no shell interpolation; only configure commands you trust. For a project with no test command, an empty `checks = []` is allowed, but the README recommends adding a meaningful test/lint/build command before enabling automatic pushes.

## Start the MCP server in Antigravity

The sample `mcp_config.example.json` shows a local stdio server entry. Replace the example executable/config paths with absolute paths on your computer and merge its `mcpServers` entry into Antigravity's config at `~/.gemini/config/mcp_config.json` (or install through Antigravity's MCP settings). Restart/reload the MCP server. The MCP server exposes:

- `list_projects`
- `submit_coding_task(project, task)`
- `queue_status`
- `get_task(task_id)`

It only enqueues tasks and reads queue state; the worker performs code changes/publishing.

## Run it

Terminal 1, keep the worker running:

```bash
agy-autopilot worker --watch
```

Then queue from a shell:

```bash
agy-autopilot enqueue --project my_app "Add a settings screen with dark mode and tests"
agy-autopilot status
```

Or ask the Antigravity MCP agent to call `submit_coding_task` with the registered project name and task description. The worker must be running for queued work to start. Completed task records are in `~/.local/share/agy-autopilot/queue/done/`; failed records are in `failed/`.

## Safety and limitations

- Uses the official SDK/local-model route; no private Antigravity API reverse engineering.
- The model gets only directory/search/read/create/edit tools, scoped to a temporary worktree. It has no shell, network-search, commit, push, or credential tool.
- The controller runs configured checks, `git diff --check`, and a heuristic secret scan before commit/push. A heuristic scan is not a substitute for a dedicated secret scanner or code review.
- Every successful publish is a separate feature branch. Review/merge it through your normal GitHub workflow; protected branches remain untouched.
- Existing uncommitted changes in your project stay untouched because work happens in a separate worktree.
- The framework was validated locally for its queue and Git safety helpers. A real SDK generation and remote push still require installation of the SDK/model, a configured project and checks, and GitHub login on the computer that runs it.
- This is a local worker, not an always-on hosted service. To process tasks after reboot, configure your OS to start the worker only after you have reviewed this policy.
