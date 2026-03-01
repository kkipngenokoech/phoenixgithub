# PhoenixGitHub

PhoenixGitHub is an always-on AI agent that picks up labeled GitHub issues, implements code changes in a branch, runs validation, and opens a pull request for human review.

## What You Get

- Hands-free issue pickup using labels (`ai:ready`, `ai:revise`).
- Structured pipeline: plan, implement, test, PR.
- Automatic state transitions on issues (`ai:in-progress`, `ai:review`, `ai:failed`, `ai:done`).
- Retry and revise flow for failed runs.
- Interactive first-time setup with `phoenixgithub init`.

## Requirements

- Python `3.11+`
- A GitHub Personal Access Token (PAT)
- Access to an LLM provider/API key (Anthropic/OpenAI-compatible via config)

## Quick Start (Pip Users)

### 1) Install

```bash
pip install phoenixgithub
```

### 2) Configure interactively

```bash
phoenixgithub init
```

This creates a `.env` in your current directory and prompts for required credentials, hiding secret inputs.

### 3) Confirm configuration

```bash
phoenixgithub status
```

### 4) Start the watcher

```bash
phoenixgithub watch
```

## How The Workflow Runs

When an issue has `ai:ready` (or `ai:revise`), PhoenixGitHub:

1. Moves the issue to `ai:in-progress`.
2. Prepares a working branch (`phoenix/issue-<number>`).
3. Plans changes with the planner agent.
4. Applies code updates with the coder agent.
5. Runs validation/tests with the tester agent.
6. Commits and pushes changes.
7. Creates or reuses a PR.
8. Moves the issue to `ai:review` on success, or `ai:failed` on failure.

## Label State Machine

```text
ai:ready / ai:revise -> ai:in-progress -> ai:review -> ai:done
                                       -> ai:failed -> ai:revise (optional auto-revise)
```

Only one AI state label is kept on the issue at a time.

## CLI Commands

- `phoenixgithub init` - interactive setup wizard that writes `.env`.
- `phoenixgithub watch` - daemon mode; continuously polls and dispatches issues.
- `phoenixgithub run-issue <number>` - one-shot run for a single issue.
- `phoenixgithub status` - show watcher state and recent runs.
- `phoenixgithub reset-issue <number>` - clear local dispatch lock for an issue.

## Configuration Reference

Most users should run `phoenixgithub init`. If you prefer manual setup, copy `.env.example` and fill the values.

Core variables:

- `GITHUB_TOKEN` - GitHub PAT used for issue/PR/label operations.
- `GITHUB_REPO` - target repository in `owner/repo` format.
- `LLM_PROVIDER` - model provider, for example `anthropic`.
- `LLM_MODEL` - model identifier accepted by your endpoint.
- `LLM_API_KEY` - API key for the selected provider/gateway.
- `POLL_INTERVAL` - watcher polling interval in seconds.
- `MAX_CONCURRENT_RUNS` - max watcher dispatches (execution is serialized per local clone).

Agent behavior variables:

- `TEST_COMMAND` - command run by tester (defaults to pytest command).
- `AUTO_REVISE_ON_TEST_FAILURE` - enables automatic relabel to `ai:revise`.
- `AUTO_REVISE_MAX_CYCLES` - cap for auto-revise loops.
- `NO_PROGRESS_ROOT_CAUSE_REPEAT_LIMIT` - stops repeated root-cause loops sooner.
- `REVISE_INCREMENTAL` - incremental branch/worktree handling for revise runs.
- `ALLOW_NO_TESTS` - treats pytest exit 5 as pass when enabled.
- `VALIDATION_PROFILE` - `auto`, `python`, `frontend`, or `generic`.

Tracing variables:

- `LANGCHAIN_TRACING_V2`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT` (commonly `phoenix-${GITHUB_REPO}`)

## GitHub Token Permissions

Use a token that can read/write issues, pull requests, and repository contents. If you use fine-grained PATs, ensure:

- Repository contents: read/write
- Issues: read/write
- Pull requests: read/write
- Workflows: read/write (if installing workflow helpers)
- Metadata: read-only

## Common Usage Pattern

1. Create or choose an issue in your repo.
2. Add label `ai:ready`.
3. Run `phoenixgithub watch`.
4. Review the created PR once issue becomes `ai:review`.
5. Merge PR and move issue to done (or use your merge workflow automation).

## Troubleshooting

- Missing config: run `phoenixgithub init` again or check `.env`.
- Issue not picked up: verify issue has `ai:ready` or `ai:revise`.
- Unauthorized API calls: re-check token/API key and scopes.
- Stuck dispatch state: run `phoenixgithub reset-issue <number>`.
- Local workspace confusion after many runs: clean `WORKSPACE_DIR` and restart watcher.

## Safety and Guardrails

- AI state labels are mutually exclusive.
- Path traversal protection blocks writes outside the repo root.
- New folder guardrail requires a meaningful `README.md`.
- Failure analyst posts guidance when runs fail and can trigger controlled revise cycles.

## Project Structure (for contributors)

```text
src/phoenixgithub/
  cli.py            # CLI commands
  config.py         # environment configuration model
  github_client.py  # GitHub + git operations
  orchestrator.py   # plan/implement/test/pr pipeline
  watcher.py        # polling + dispatch
  state.py          # local run/watcher state
  agents/           # planner/coder/tester/pr/failure analyst
```

## Maintainer Docs

Release and package publishing instructions live in `RELEASING.md`.
Internal operations and architecture runbook lives in `INTERNAL_README.md`.
Documentation index lives in `docs/README.md`.
