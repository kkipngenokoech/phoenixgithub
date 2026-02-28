"""CLI entry point — start the daemon, run once, or check status."""

from __future__ import annotations

import logging
import sys
import threading

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
    console.print(f"  Label:    {config.labels.ready}")
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
