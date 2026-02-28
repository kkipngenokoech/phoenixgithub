# PhoenixGitHub

Always-on AI agent that picks up GitHub issues, implements them, and creates PRs for human review.

## How It Works

```
PM creates issue        AI picks it up         AI creates PR         Human reviews
with ai:ready    →    clones, branches,   →   pushes to remote  →   merges to main
label                  plans, codes, tests     with full summary
```

### Label State Machine

```
ai:ready  →  ai:in-progress  →  ai:review  →  (human merges)  →  ai:done
                                    ↓
                              ai:failed (on error)
```

### Architecture (from slides)

```
┌──────────── TRIGGER LAYER ────────────┐
│  Watcher: polls for ai:ready issues   │
└───────────────┬───────────────────────┘
                │ dispatches
┌───────────────▼─── ORCHESTRATION ─────┐
│  Plan → Implement → Test → PR         │
│  (verify-reject-retry loop)           │
└───────────────┬───────────────────────┘
                │ delegates to
┌───────────────▼─── AGENT LAYER ───────┐
│  Planner    (read-only)               │
│  Coder      (read + write)            │
│  Tester     (read + run tests)        │
│  PR Agent   (read + GitHub)           │
└───────────────┬───────────────────────┘
                │ pushes to
┌───────────────▼─── GITHUB ────────────┐
│  Feature branch → PR → Human review   │
└───────────────────────────────────────┘
```

## Setup

### 1. Install

```bash
cd phoenixgithub
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your GitHub token, repo, and LLM API key
```

**GitHub Token** needs these permissions:
- `repo` (full control of private repos)
- `issues` (read/write)
- `pull_requests` (read/write)

### 3. Create Labels

The watcher auto-creates these labels on first run:
- `ai:ready` — issue is ready for AI to pick up
- `ai:in-progress` — AI is working on it
- `ai:review` — PR created, awaiting human review
- `ai:revise` — human requested changes
- `ai:done` — completed and merged
- `ai:failed` — AI could not complete the task

## Usage

### Daemon Mode (always-on)

```bash
phoenixgithub watch
```

Polls your repo every 60s (configurable) for issues labeled `ai:ready`. When found:
1. Clones the repo (or pulls latest)
2. Creates a feature branch (`phoenix/issue-42`)
3. Planner agent analyzes the issue and codebase
4. Coder agent implements the changes
5. Tester agent runs tests (retries on failure)
6. PR agent creates a pull request with summary
7. Labels the issue `ai:review`

### One-Shot Mode

```bash
phoenixgithub run-issue 42
```

Runs the pipeline for a single issue without polling.

### Check Status

```bash
phoenixgithub status
```

### Reset a Stuck Issue

```bash
phoenixgithub reset-issue 42
```

## Project Structure

```
phoenixgithub/
├── src/phoenixgithub/
│   ├── cli.py              # CLI entry point
│   ├── config.py            # Environment-based configuration
│   ├── models.py            # Run, Step, WatcherState models
│   ├── provider.py          # LLM provider factory
│   ├── github_client.py     # GitHub API + git operations
│   ├── watcher.py           # Trigger layer (polls for issues)
│   ├── state.py             # State persistence (run.json)
│   ├── orchestrator.py      # Pipeline execution engine
│   └── agents/
│       ├── base.py          # Base agent abstraction
│       ├── planner.py       # Read-only: analyzes issue + codebase
│       ├── coder.py         # Read+write: implements changes
│       ├── tester.py        # Read+run: executes tests
│       └── pr_agent.py      # Read+GitHub: writes PR description
├── workspace/               # Cloned repos live here
├── .env.example
├── pyproject.toml
└── requirements.txt
```

## Key Design Decisions

1. **Real clones, not staging copies** — agents work on actual git clones with remotes intact, so push and PR creation work for real.

2. **Labels as state machine** — GitHub labels drive the workflow. No external database needed for coordination.

3. **Verify-reject-retry loop** — if tests fail, the tester feeds back specific errors to the coder, which retries up to N times.

4. **Agent specialization** — each agent has a constrained role. The planner can't write code, the tester can't fix bugs.

5. **Orchestrator never implements** — it only dispatches to agents and manages transitions.

6. **Run state persisted as JSON** — survives crashes, can be inspected by any tool.
