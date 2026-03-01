"""Watcher — polls GitHub for issues labeled ai:ready and dispatches runs."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from github.Issue import Issue

from phoenixgithub.config import Config
from phoenixgithub.github_client import GitHubClient
from phoenixgithub.models import Run, RunStatus
from phoenixgithub.state import StateManager

logger = logging.getLogger(__name__)


class Watcher:
    """Trigger layer: polls GitHub issues on an interval and dispatches work."""

    def __init__(
        self,
        config: Config,
        github: GitHubClient,
        state: StateManager,
        on_dispatch: Optional[Callable[[Run], None]] = None,
    ) -> None:
        self.config = config
        self.github = github
        self.state = state
        self._on_dispatch = on_dispatch
        self._running = False

    def poll_once(self) -> list[Run]:
        """Single poll cycle: find ready issues, dispatch new runs."""
        dispatched_runs: list[Run] = []

        if self.state.watcher.active_runs >= self.config.github.max_concurrent_runs:
            logger.info(
                f"At concurrency limit ({self.state.watcher.active_runs}/"
                f"{self.config.github.max_concurrent_runs}) — skipping poll"
            )
            return dispatched_runs

        ready_issues = self.github.get_ready_issues()
        revise_issues = self.github.get_revise_issues()

        # ai:revise is a first-class trigger; dedupe if an issue has both labels.
        triggers: dict[int, tuple[Issue, str]] = {}
        for issue in ready_issues:
            triggers[issue.number] = (issue, self.config.labels.ready)
        for issue in revise_issues:
            triggers.setdefault(issue.number, (issue, self.config.labels.revise))

        for issue, from_label in triggers.values():
            if self.state.is_dispatched(issue.number):
                logger.info(f"Issue #{issue.number} already dispatched — skipping")
                continue

            run = Run(
                repo=self.config.github.repo,
                issues=[issue.number],
                branch_name=f"phoenix/issue-{issue.number}",
            )

            self.state.mark_dispatched(issue.number, run.run_id)
            self.state.save_run(run)

            self.github.transition_label(
                issue.number,
                from_label,
                self.config.labels.in_progress,
            )
            self.github.comment_on_issue(
                issue.number,
                f"🤖 **Phoenix AI** picked up this issue.\n\n"
                f"**Run ID:** `{run.run_id}`\n"
                f"**Branch:** `{run.branch_name}`\n\n"
                f"Triggered by label: `{from_label}`\n\n"
                f"Working on it now...",
            )

            logger.info(f"Dispatched run {run.run_id} for issue #{issue.number}")
            dispatched_runs.append(run)

        self.state.watcher.last_poll = datetime.now(timezone.utc)
        self.state.save_watcher_state()
        return dispatched_runs

    def run_loop(self, on_dispatch: Callable[[Run], None] | None = None) -> None:
        """Blocking poll loop — runs until stopped."""
        handler = on_dispatch or self._on_dispatch
        if not handler:
            raise ValueError("No dispatch handler provided")

        self._running = True
        interval = self.config.github.poll_interval

        logger.info(
            f"Watcher started — polling {self.config.github.repo} "
            f"every {interval}s for '{self.config.labels.ready}' and "
            f"'{self.config.labels.revise}' issues"
        )

        while self._running:
            try:
                runs = self.poll_once()
                for run in runs:
                    handler(run)
            except KeyboardInterrupt:
                logger.info("Watcher stopped by user")
                self._running = False
                break
            except Exception as e:
                logger.error(f"Poll error: {e}", exc_info=True)

            if self._running:
                time.sleep(interval)

    def stop(self) -> None:
        self._running = False
