# PhoenixGitHub

PhoenixGitHub is an always-on AI engineering agent for GitHub repositories.  
It watches labeled issues, plans and implements changes, validates the result, and opens a pull request for human review.

## Project Description

PhoenixGitHub turns issue labels into a lightweight development workflow:

- Pick up work from `ai:ready` or `ai:revise`.
- Run a structured pipeline: plan -> code -> test -> PR.
- Keep issue state synchronized with labels (`ai:in-progress`, `ai:review`, `ai:failed`, `ai:done`).
- Provide guided retry loops when a run fails.
- Support interactive first-time setup with `phoenixgithub init`.

This is designed for teams who want AI automation in normal GitHub workflows, without replacing human approval on merges.

## Installation

```bash
pip install phoenixgithub
```

## Quick Start

### 1) Initialize configuration

```bash
phoenixgithub init
```

The setup wizard writes `.env` in your current directory and prompts for required credentials with hidden input for secrets.

### 2) Verify configuration

```bash
phoenixgithub status
```

### 3) Start the watcher

```bash
phoenixgithub watch
```

### 4) Trigger an issue run

In your GitHub repo, add label `ai:ready` to an issue. PhoenixGitHub will pick it up automatically.

## End-to-End Flow

When an issue enters `ai:ready` or `ai:revise`, PhoenixGitHub:

1. Transitions the issue to `ai:in-progress`.
2. Prepares a working branch (`phoenix/issue-<number>`).
3. Builds a plan from issue details and existing code.
4. Applies code changes through the coder agent.
5. Runs validation and test checks.
6. Commits and pushes results.
7. Creates (or reuses) a pull request.
8. Transitions the issue to:
   - `ai:review` on success
   - `ai:failed` on failure

## Label State Machine

```text
ai:ready / ai:revise -> ai:in-progress -> ai:review -> ai:done
                                       -> ai:failed -> ai:revise (optional auto-revise)
```

AI state labels are enforced as mutually exclusive.

## CLI Reference

| Command | Purpose |
| --- | --- |
| `phoenixgithub init` | Interactive setup wizard that creates `.env` |
| `phoenixgithub watch` | Run the daemon and process labeled issues continuously |
| `phoenixgithub run-issue <number>` | One-shot run for a single issue |
| `phoenixgithub status` | Show watcher state and recent runs |
| `phoenixgithub reset-issue <number>` | Clear local dispatch lock for an issue |

## Key Features

- **Issue-driven automation**: labels control the entire workflow.
- **Deterministic orchestration**: clear step boundaries (plan, implement, test, PR).
- **Failure feedback loop**: failure analyst comments with suggested fixes.
- **Revise mode**: targeted retries using `ai:revise`.
- **Validation profiles**: `auto`, `python`, `frontend`, `generic`.
- **Safety rails**: path protections, label exclusivity, no-progress cycle limits.

## Configuration

Most users should use `phoenixgithub init`. Manual setup is also supported using `.env.example`.

### Core Variables

- `GITHUB_TOKEN`: GitHub PAT used for issue/PR/label operations.
- `GITHUB_REPO`: repository in `owner/repo` format.
- `LLM_PROVIDER`: model provider (for example `anthropic`).
- `LLM_MODEL`: model ID accepted by your endpoint.
- `LLM_API_KEY`: provider or gateway API key.
- `POLL_INTERVAL`: watcher poll interval in seconds.
- `MAX_CONCURRENT_RUNS`: watcher dispatch pressure.

### Agent Behavior Variables

- `TEST_COMMAND`: command used by tester.
- `AUTO_REVISE_ON_TEST_FAILURE`: auto-relable to `ai:revise`.
- `AUTO_REVISE_MAX_CYCLES`: max auto-revise attempts.
- `NO_PROGRESS_ROOT_CAUSE_REPEAT_LIMIT`: stop repeated root causes sooner.
- `REVISE_INCREMENTAL`: reuse branch/worktree on revise runs.
- `ALLOW_NO_TESTS`: treat pytest exit 5 as pass if enabled.
- `VALIDATION_PROFILE`: `auto`, `python`, `frontend`, `generic`.

### Tracing Variables

- `LANGCHAIN_TRACING_V2`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT` (commonly `phoenix-${GITHUB_REPO}`)

## GitHub Token Permissions

Your token should allow issue, PR, and content operations. For fine-grained PATs, recommended permissions are:

- Repository contents: read/write
- Issues: read/write
- Pull requests: read/write
- Workflows: read/write (if installing workflow helpers)
- Metadata: read-only

## Example Usage Pattern

1. Create or select an issue in your target repo.
2. Add label `ai:ready`.
3. Run `phoenixgithub watch`.
4. Wait for label transition to `ai:review`.
5. Review and merge the created PR.
6. Mark the issue done (or automate done labeling with your workflow).

## Troubleshooting

- **Issue not picked up**: verify `ai:ready` or `ai:revise` is present.
- **Auth errors**: verify PAT scopes and LLM credentials.
- **Stuck local dispatch state**: run `phoenixgithub reset-issue <number>`.
- **Workspace inconsistencies**: clean `WORKSPACE_DIR` and restart watcher.
- **No tests collected**: consider `ALLOW_NO_TESTS=true` for non-test repos.

## Safety and Guardrails

- Path traversal prevention blocks writes outside repository root.
- AI labels are mutually exclusive during state transitions.
- New folder guardrail requires meaningful `README.md`.
- Failure analyst provides structured root-cause feedback.
- Revise loops are bounded by configurable cycle limits.

## Project Structure

```text
src/phoenixgithub/
  cli.py            # CLI commands
  config.py         # configuration model from environment
  github_client.py  # GitHub API and git operations
  orchestrator.py   # plan/implement/test/pr pipeline
  watcher.py        # polling and dispatch
  state.py          # local run and watcher state
  agents/           # planner/coder/tester/pr/failure analyst
scripts/
  pre_release.py                    # local release checks
  create_labels.py                  # create/ensure AI labels in target repo
  install_merge_done_workflow.py    # install merge->ai:done workflow
  reset_repo_state.py               # clear local run/clone state for current repo
.github/workflows/
  publish-pypi.yml                  # GitHub Release -> PyPI publish (OIDC)
docs/
  README.md                         # docs index
INTERNAL_README.md                  # internal architecture and operations guide
RELEASING.md                        # release runbook
```

## Maintainer Documentation

- `INTERNAL_README.md`: architecture and operations runbook.
- `RELEASING.md`: release and publishing process.
- `docs/README.md`: documentation index.
