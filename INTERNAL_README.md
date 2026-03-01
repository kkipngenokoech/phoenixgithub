# PhoenixGitHub Internal README

This document is for maintainers/operators of `phoenixgithub`. It complements:

- `README.md` (end-user usage)
- `RELEASING.md` (release/publishing specifics)

## 1. System Overview

PhoenixGitHub is a label-driven GitHub automation agent that:

1. Polls for actionable issues (`ai:ready`, `ai:revise`).
2. Executes an orchestration pipeline (plan -> implement -> test -> PR).
3. Transitions issue labels as state.
4. Posts run updates back to GitHub issue comments.

Core modules:

- `src/phoenixgithub/watcher.py`: polling + dispatch loop.
- `src/phoenixgithub/orchestrator.py`: pipeline coordinator.
- `src/phoenixgithub/github_client.py`: GitHub API + git operations.
- `src/phoenixgithub/state.py`: local state and run persistence.
- `src/phoenixgithub/agents/*`: planner/coder/tester/pr/failure analyst.
- `src/phoenixgithub/cli.py`: CLI entry points.

## 2. Label State Machine

Primary state labels:

- `ai:ready` - issue is queued for a fresh run.
- `ai:in-progress` - currently being worked.
- `ai:review` - PR ready for human review.
- `ai:revise` - targeted rerun after feedback/failure.
- `ai:done` - merged/completed.
- `ai:failed` - run failed and needs intervention/retry.

Behavior:

- Watcher polls both `ai:ready` and `ai:revise`.
- Labels are enforced as mutually exclusive AI states.
- `ai:revise` can be triggered manually or automatically, depending on config.

## 3. Runtime Flow

Per run sequence:

1. Resolve issue context and comments.
2. Prepare local workspace clone/branch.
3. Planner generates implementation plan.
4. Coder writes files with guardrails.
5. Tester validates based on profile/commands.
6. Commit and push changes.
7. Create or reuse PR.
8. Label issue to `ai:review` on success; otherwise failure path.

Failure path:

- Run marked failed.
- Failure analyst generates root cause and suggestions.
- Issue/comment updated.
- Optional auto-revise relabeling with cycle limits.

## 4. Concurrency Model

Important: local execution is serialized in the orchestrator using a lock.

Why:

- A single local clone/worktree per repo can conflict across concurrent checkouts/resets.
- Serialization prevents branch/reset collisions between runs.

Notes:

- `MAX_CONCURRENT_RUNS` controls watcher dispatch pressure, but execution still uses a safety lock for clone/worktree integrity.

## 5. Guardrails and Safety

Current protections include:

- Path traversal prevention for file writes (no writes outside repo root).
- New-folder README guardrail (requires meaningful `README.md`).
- AI state label exclusivity during transitions.
- Applied-file coverage warnings/auto-staging fallback for omitted changed files.
- No-progress and auto-revise cycle caps to avoid infinite loops.
- Validation profiles (`auto`, `python`, `frontend`, `generic`).

## 6. Repository Structure

```text
src/phoenixgithub/
  cli.py
  config.py
  github_client.py
  watcher.py
  orchestrator.py
  state.py
  agents/
scripts/
  create_labels.py
  install_merge_done_workflow.py
  reset_repo_state.py
  pre_release.py
.github/workflows/
  publish-pypi.yml
```

## 7. Configuration and Environment

Source of truth:

- `.env.example` (template)
- `.env` (local runtime config)

High-impact variables:

- `GITHUB_TOKEN`, `GITHUB_REPO`
- `POLL_INTERVAL`, `MAX_CONCURRENT_RUNS`
- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`
- `TEST_COMMAND`, `BUILD_COMMAND`
- `AUTO_REVISE_ON_TEST_FAILURE`, `AUTO_REVISE_MAX_CYCLES`
- `NO_PROGRESS_ROOT_CAUSE_REPEAT_LIMIT`
- `REVISE_INCREMENTAL`
- `ALLOW_NO_TESTS`
- `VALIDATION_PROFILE`
- `WORKSPACE_DIR`, `STATE_FILE`, `LOG_LEVEL`
- `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`

## 8. Operational Commands (Makefile)

Day-to-day:

- `make watch` - run watcher daemon.
- `make status` - show current state.
- `make run-issue ISSUE=<n>` - one-shot issue run.

Repo bootstrap/onboarding:

- `make labels` - ensure AI labels exist.
- `make setup-actions` - install merge->done workflow into target repo.
- `make onboard` - clean + labels + actions + status.

State/workspace cleanup:

- `make reset-state` - remove local watcher state file.
- `make clean-repo-state` - clear local run/clone state for configured repo.
- `make clean-workspace-all` - remove local `workspace/`.

Release:

- `make pre-release` - local pre-release checks.
- `make pre-release TAG=vX.Y.Z` - include version/tag consistency check.
- `make release TAG=vX.Y.Z` - pre-checks + GitHub release creation.

## 9. Release and Publishing

Publishing is GitHub-driven:

- Workflow: `.github/workflows/publish-pypi.yml`
- Trigger: GitHub release publish (or manual workflow dispatch)
- Auth: PyPI Trusted Publishing (OIDC)

PyPI setup requirement:

- Configure PyPI Trusted/Pending Publisher with:
  - project `phoenixgithub`
  - owner/repo
  - workflow `publish-pypi.yml`

Recommended release sequence:

1. Bump `pyproject.toml` version.
2. Run `make release TAG=vX.Y.Z`.
3. Confirm workflow success in GitHub Actions.
4. Verify `pip install -U phoenixgithub`.

## 10. Troubleshooting Playbook

Issue not picked:

- Verify label is `ai:ready` or `ai:revise`.
- Check watcher logs and local state.
- Use `make reset-state` if dispatch lock is stale.

Git checkout/reset conflicts:

- Ensure watcher restarted after recent orchestrator updates.
- Run `make clean-workspace-all` and restart watcher.

Auth failures:

- GitHub: re-check PAT scopes and repo access.
- LLM: confirm model ID and key against endpoint.

No tests collected loop:

- Set `ALLOW_NO_TESTS=true` where appropriate.
- Confirm `VALIDATION_PROFILE` is correct for repo type.

PR or commit anomalies:

- Check commit logs for uncovered changed-path warnings.
- Validate `applied_files` behavior and auto-staging output.

## 11. Local Validation Checklist Before Big Changes

1. Run `python -m py_compile` on changed Python files.
2. Review lints on touched files.
3. Smoke test with:
   - `phoenixgithub status`
   - one test issue with `ai:ready`
4. Confirm labels and PR lifecycle in target repo.

## 12. Change Management Recommendations

- Keep user docs in `README.md` concise and task-oriented.
- Keep maintainer procedures in this file and `RELEASING.md`.
- Prefer additive configuration and backward-compatible defaults.
- When changing label semantics, update watcher/orchestrator/docs together.
