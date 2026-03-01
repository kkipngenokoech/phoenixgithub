"""CLI entry point — start the daemon, run once, or check status."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from phoenixgithub.config import Config
from phoenixgithub.github_client import GitHubClient
from phoenixgithub.models import Run, RunStatus
from phoenixgithub.orchestrator import Orchestrator
from phoenixgithub.state import StateManager
from phoenixgithub.watcher import Watcher

console = Console()


def _prompt_secret(label: str, default: str = "") -> str:
    """Prompt for a secret value without echoing input."""
    return click.prompt(label, default=default, hide_input=True, show_default=bool(default)).strip()


def _prompt_text(label: str, default: str = "") -> str:
    """Prompt for a standard text value."""
    return click.prompt(label, default=default, show_default=bool(default)).strip()


def _prompt_int(label: str, default: int) -> int:
    """Prompt for an integer value."""
    return click.prompt(label, default=default, type=int, show_default=True)


def _prompt_bool(label: str, default: bool) -> bool:
    """Prompt for a yes/no value."""
    return click.confirm(label, default=default, show_default=True)


def _build_env_contents(values: dict[str, str]) -> str:
    """Render a complete .env file from prompted values."""
    return (
        "# ── GitHub ──────────────────────────────────────────\n"
        f"GITHUB_TOKEN={values['GITHUB_TOKEN']}\n"
        f"GITHUB_REPO={values['GITHUB_REPO']}\n"
        "\n"
        "# ── Polling ─────────────────────────────────────────\n"
        f"POLL_INTERVAL={values['POLL_INTERVAL']}\n"
        f"MAX_CONCURRENT_RUNS={values['MAX_CONCURRENT_RUNS']}\n"
        "\n"
        "# ── LLM ─────────────────────────────────────────────\n"
        f"LLM_PROVIDER={values['LLM_PROVIDER']}\n"
        f"LLM_MODEL={values['LLM_MODEL']}\n"
        f"LLM_API_KEY={values['LLM_API_KEY']}\n"
        f"{values['LLM_BASE_URL_LINE']}\n"
        "\n"
        "# ── LangSmith (Tracing) ─────────────────────────────\n"
        f"LANGCHAIN_TRACING_V2={values['LANGCHAIN_TRACING_V2']}\n"
        f"LANGCHAIN_API_KEY={values['LANGCHAIN_API_KEY']}\n"
        f"LANGCHAIN_PROJECT={values['LANGCHAIN_PROJECT']}\n"
        "# LANGCHAIN_ENDPOINT=https://api.smith.langchain.com\n"
        "\n"
        "# ── Agent ───────────────────────────────────────────\n"
        f"TEST_COMMAND={values['TEST_COMMAND']}\n"
        f"{values['BUILD_COMMAND_LINE']}\n"
        f"AUTO_REVISE_ON_TEST_FAILURE={values['AUTO_REVISE_ON_TEST_FAILURE']}\n"
        f"AUTO_REVISE_MAX_CYCLES={values['AUTO_REVISE_MAX_CYCLES']}\n"
        f"NO_PROGRESS_ROOT_CAUSE_REPEAT_LIMIT={values['NO_PROGRESS_ROOT_CAUSE_REPEAT_LIMIT']}\n"
        f"REVISE_INCREMENTAL={values['REVISE_INCREMENTAL']}\n"
        f"ALLOW_NO_TESTS={values['ALLOW_NO_TESTS']}\n"
        f"VALIDATION_PROFILE={values['VALIDATION_PROFILE']}\n"
        "\n"
        "# ── Paths ───────────────────────────────────────────\n"
        f"WORKSPACE_DIR={values['WORKSPACE_DIR']}\n"
        f"STATE_FILE={values['STATE_FILE']}\n"
        f"LOG_LEVEL={values['LOG_LEVEL']}\n"
    )


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


def _build_stack(config: Config) -> tuple[GitHubClient, StateManager, Orchestrator, Watcher]:
    github = GitHubClient(config)
    state = StateManager(config.state_file, config.workspace_dir)
    orchestrator = Orchestrator(config, github, state)
    watcher = Watcher(config, github, state)
    return github, state, orchestrator, watcher


@click.group()
def main() -> None:
    """PhoenixGitHub — AI agent that picks up GitHub issues and creates PRs."""
    pass


@main.command(name="init")
@click.option("--env-file", default=".env", show_default=True, help="Path to write env config.")
@click.option("--force", is_flag=True, help="Overwrite env file if it already exists.")
def init_config(env_file: str, force: bool) -> None:
    """Interactive setup wizard that creates a ready-to-run .env file."""
    target = Path(env_file).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target

    if target.exists() and not force:
        console.print(
            f"[yellow]{target} already exists.[/yellow] Use [bold]--force[/bold] to overwrite it."
        )
        return
    target.parent.mkdir(parents=True, exist_ok=True)

    console.print("[bold green]PhoenixGitHub interactive setup[/bold green]")
    console.print(f"Writing config to: [cyan]{target}[/cyan]\n")

    github_token = _prompt_secret("GitHub PAT (GITHUB_TOKEN)")
    github_repo = _prompt_text("GitHub repo (owner/repo)", "owner/repo")
    poll_interval = _prompt_int("Poll interval in seconds", 60)
    max_concurrent_runs = _prompt_int("Max concurrent watcher dispatches", 2)

    llm_provider = _prompt_text("LLM provider", "anthropic")
    llm_model = _prompt_text("LLM model", "claude-sonnet-4-20250514-v1:0")
    llm_api_key = _prompt_secret("LLM API key (LLM_API_KEY)")
    use_custom_base = _prompt_bool("Use a custom LLM base URL?", False)
    llm_base_url = _prompt_text("LLM base URL", "").strip() if use_custom_base else ""

    enable_tracing = _prompt_bool("Enable LangSmith tracing?", True)
    langchain_api_key = ""
    if enable_tracing:
        langchain_api_key = _prompt_secret("LangSmith API key (LANGCHAIN_API_KEY)")
    langchain_project_default = f"phoenix-{github_repo}" if github_repo and "/" in github_repo else "phoenix-local"
    langchain_project = _prompt_text("LangSmith project name", langchain_project_default)

    console.print()
    configure_advanced = _prompt_bool("Configure advanced options now?", False)
    if configure_advanced:
        test_command = _prompt_text("Test command", "pytest --import-mode=importlib --rootdir=.")
        build_command = _prompt_text("Build command (optional, blank to disable)", "")
        auto_revise_on_test_failure = _prompt_bool("Auto-revise on test failure?", True)
        auto_revise_max_cycles = _prompt_int("Auto-revise max cycles", 3)
        no_progress_limit = _prompt_int("No-progress repeat limit", 2)
        revise_incremental = _prompt_bool("Use incremental revise mode?", True)
        allow_no_tests = _prompt_bool("Allow pytest exit 5 (no tests collected)?", False)
        validation_profile = _prompt_text("Validation profile (auto/python/frontend/generic)", "auto")
        workspace_dir = _prompt_text("Workspace directory", "./workspace")
        state_file = _prompt_text("State file path", "./.watcher-state.json")
        log_level = _prompt_text("Log level", "INFO")
    else:
        test_command = "pytest --import-mode=importlib --rootdir=."
        build_command = ""
        auto_revise_on_test_failure = True
        auto_revise_max_cycles = 3
        no_progress_limit = 2
        revise_incremental = True
        allow_no_tests = False
        validation_profile = "auto"
        workspace_dir = "./workspace"
        state_file = "./.watcher-state.json"
        log_level = "INFO"

    values = {
        "GITHUB_TOKEN": github_token,
        "GITHUB_REPO": github_repo,
        "POLL_INTERVAL": str(poll_interval),
        "MAX_CONCURRENT_RUNS": str(max_concurrent_runs),
        "LLM_PROVIDER": llm_provider,
        "LLM_MODEL": llm_model,
        "LLM_API_KEY": llm_api_key,
        "LLM_BASE_URL_LINE": f"LLM_BASE_URL={llm_base_url}" if llm_base_url else "# LLM_BASE_URL=",
        "LANGCHAIN_TRACING_V2": "true" if enable_tracing else "false",
        "LANGCHAIN_API_KEY": langchain_api_key if enable_tracing else "lsv2_your_langsmith_api_key",
        "LANGCHAIN_PROJECT": langchain_project,
        "TEST_COMMAND": test_command,
        "BUILD_COMMAND_LINE": f"BUILD_COMMAND={build_command}" if build_command else "# BUILD_COMMAND=",
        "AUTO_REVISE_ON_TEST_FAILURE": "true" if auto_revise_on_test_failure else "false",
        "AUTO_REVISE_MAX_CYCLES": str(auto_revise_max_cycles),
        "NO_PROGRESS_ROOT_CAUSE_REPEAT_LIMIT": str(no_progress_limit),
        "REVISE_INCREMENTAL": "true" if revise_incremental else "false",
        "ALLOW_NO_TESTS": "true" if allow_no_tests else "false",
        "VALIDATION_PROFILE": validation_profile,
        "WORKSPACE_DIR": workspace_dir,
        "STATE_FILE": state_file,
        "LOG_LEVEL": log_level.upper(),
    }
    target.write_text(_build_env_contents(values), encoding="utf-8")

    masked_token = f"{github_token[:6]}..." if github_token else "(empty)"
    masked_llm_key = f"{llm_api_key[:6]}..." if llm_api_key else "(empty)"
    console.print("\n[green]Configuration saved.[/green]")
    console.print(f"- Repo: [cyan]{github_repo}[/cyan]")
    console.print(f"- GitHub token: [dim]{masked_token}[/dim]")
    console.print(f"- LLM provider/model: [cyan]{llm_provider} / {llm_model}[/cyan]")
    console.print(f"- LLM key: [dim]{masked_llm_key}[/dim]")
    console.print("\nNext steps:")
    console.print("1) [bold]phoenixgithub status[/bold]")
    console.print("2) [bold]phoenixgithub watch[/bold]")


@main.command()
@click.option("--log-level", default=None, help="Log level (DEBUG, INFO, WARNING)")
def watch(log_level: str | None) -> None:
    """Start the watcher daemon — polls for ai:ready issues and runs the pipeline."""
    config = Config.from_env()
    _setup_logging(log_level or config.log_level)

    if not config.github.token:
        console.print("[red]GITHUB_TOKEN is required. Set it in .env or environment.[/red]")
        sys.exit(1)
    if not config.github.repo:
        console.print("[red]GITHUB_REPO is required (owner/repo). Set it in .env or environment.[/red]")
        sys.exit(1)

    github, state, orchestrator, watcher = _build_stack(config)

    console.print(f"[bold green]PhoenixGitHub Watcher[/bold green]")
    console.print(f"  Repo:     {config.github.repo}")
    console.print(f"  Interval: {config.github.poll_interval}s")
    console.print(f"  Labels:   {config.labels.ready}, {config.labels.revise}")
    console.print()

    def dispatch(run: Run) -> None:
        console.print(f"[yellow]Dispatched run {run.run_id} for issue #{run.issues[0]}[/yellow]")
        thread = threading.Thread(
            target=_run_in_thread, args=(orchestrator, state, run), daemon=True
        )
        thread.start()

    try:
        watcher.run_loop(on_dispatch=dispatch)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


@main.command()
@click.argument("issue_number", type=int)
@click.option("--log-level", default=None)
def run_issue(issue_number: int, log_level: str | None) -> None:
    """Run the pipeline for a single issue (one-shot, no polling)."""
    config = Config.from_env()
    _setup_logging(log_level or config.log_level)

    if not config.github.token or not config.github.repo:
        console.print("[red]GITHUB_TOKEN and GITHUB_REPO are required.[/red]")
        sys.exit(1)

    github, state, orchestrator, _ = _build_stack(config)

    run = Run(
        repo=config.github.repo,
        issues=[issue_number],
        branch_name=f"phoenix/issue-{issue_number}",
    )
    state.save_run(run)

    console.print(f"[bold]Running pipeline for issue #{issue_number}...[/bold]")

    try:
        github.transition_label(
            issue_number, config.labels.ready, config.labels.in_progress
        )
    except Exception:
        pass

    result = orchestrator.execute(run)

    if result.status == RunStatus.SUCCEEDED:
        console.print(f"[bold green]Success![/bold green] PR: {result.pr_url}")
    else:
        console.print(f"[bold red]Failed:[/bold red] {result.error}")


@main.command()
def status() -> None:
    """Show current watcher state and recent runs."""
    config = Config.from_env()
    _setup_logging("WARNING")
    _, state, _, _ = _build_stack(config)

    ws = state.watcher
    console.print(f"[bold]Watcher State[/bold]")
    console.print(f"  Active runs: {ws.active_runs}")
    console.print(f"  Last poll:   {ws.last_poll or 'never'}")
    console.print(f"  Dispatched:  {len(ws.dispatched)} issues")
    console.print()

    runs = state.list_runs()
    if not runs:
        console.print("[dim]No runs yet.[/dim]")
        return

    table = Table(title="Recent Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Issues")
    table.add_column("Status")
    table.add_column("Branch")
    table.add_column("PR")
    table.add_column("Created")

    for r in runs[:20]:
        status_style = {
            RunStatus.SUCCEEDED: "[green]succeeded[/green]",
            RunStatus.FAILED: "[red]failed[/red]",
            RunStatus.RUNNING: "[yellow]running[/yellow]",
            RunStatus.PENDING: "[dim]pending[/dim]",
        }.get(r.status, str(r.status))

        table.add_row(
            r.run_id,
            ", ".join(f"#{n}" for n in r.issues),
            status_style,
            r.branch_name or "-",
            r.pr_url or "-",
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-",
        )

    console.print(table)


@main.command()
@click.argument("issue_number", type=int)
def reset_issue(issue_number: int) -> None:
    """Clear dispatch state for an issue so it can be re-triggered."""
    config = Config.from_env()
    _setup_logging("WARNING")
    _, state, _, _ = _build_stack(config)
    state.clear_dispatched(issue_number)
    console.print(f"[green]Cleared dispatch state for issue #{issue_number}[/green]")


def _run_in_thread(orchestrator: Orchestrator, state: StateManager, run: Run) -> None:
    """Execute a run in a background thread (used by the daemon)."""
    try:
        orchestrator.execute(run)
    except Exception as e:
        logging.getLogger(__name__).error(f"Run {run.run_id} crashed: {e}", exc_info=True)
        run.status = RunStatus.FAILED
        run.error = str(e)
        state.save_run(run)
        state.mark_run_finished(run.run_id)


if __name__ == "__main__":
    main()
