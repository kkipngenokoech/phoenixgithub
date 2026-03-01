"""GitHub client — wraps PyGithub + git CLI for all GitHub operations."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from github import Github, GithubException
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository
from git import Repo
from git.exc import GitCommandError

from phoenixgithub.config import Config, LabelConfig

logger = logging.getLogger(__name__)


class GitHubClient:
    """All interactions with GitHub: issues, labels, clones, branches, PRs."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._gh = Github(config.github.token)
        self._repo: Repository = self._gh.get_repo(config.github.repo)
        self._labels = config.labels

    # ------------------------------------------------------------------
    # Issues & Labels
    # ------------------------------------------------------------------

    def get_ready_issues(self) -> list[Issue]:
        """Find all open issues with the ai:ready label."""
        issues = self._get_issues_by_label(self._labels.ready)
        logger.info(f"Found {len(issues)} issues with label '{self._labels.ready}'")
        return issues

    def get_revise_issues(self) -> list[Issue]:
        """Find all open issues with the ai:revise label."""
        issues = self._get_issues_by_label(self._labels.revise)
        logger.info(f"Found {len(issues)} issues with label '{self._labels.revise}'")
        return issues

    def _get_issues_by_label(self, label_name: str) -> list[Issue]:
        """Find all open issues with a specific label, ensuring labels exist."""
        try:
            label = self._repo.get_label(label_name)
        except GithubException:
            logger.warning(f"Label '{label_name}' not found in repo — creating it")
            self._ensure_labels()
            label = self._repo.get_label(label_name)
        return list(self._repo.get_issues(state="open", labels=[label]))

    def transition_label(self, issue_number: int, from_label: str, to_label: str) -> None:
        """Remove one label, add another — state machine transition."""
        issue = self._repo.get_issue(issue_number)
        try:
            issue.remove_from_labels(from_label)
        except GithubException:
            pass
        issue.add_to_labels(to_label)
        logger.info(f"Issue #{issue_number}: {from_label} → {to_label}")

    def add_label(self, issue_number: int, label: str) -> None:
        self._repo.get_issue(issue_number).add_to_labels(label)

    def comment_on_issue(self, issue_number: int, body: str) -> None:
        self._repo.get_issue(issue_number).create_comment(body)

    def get_issue(self, issue_number: int) -> Issue:
        return self._repo.get_issue(issue_number)

    def ensure_labels(self) -> None:
        """Public helper to ensure AI workflow labels exist."""
        self._ensure_labels()

    def _ensure_labels(self) -> None:
        """Create all AI labels if they don't exist."""
        existing = {l.name for l in self._repo.get_labels()}
        label_colors = {
            self._labels.ready: "0E8A16",
            self._labels.in_progress: "FBCA04",
            self._labels.review: "1D76DB",
            self._labels.revise: "E99695",
            self._labels.done: "0E8A16",
            self._labels.failed: "D93F0B",
        }
        for name, color in label_colors.items():
            if name not in existing:
                self._repo.create_label(name, color)
                logger.info(f"Created label: {name}")

    # ------------------------------------------------------------------
    # Clone & Branch
    # ------------------------------------------------------------------

    def ensure_clone(self, workspace_dir: str) -> str:
        """Clone the repo into workspace if not already cloned. Returns path to clone."""
        clone_path = Path(workspace_dir) / self.config.github.repo_name
        if clone_path.exists() and (clone_path / ".git").exists():
            repo = Repo(str(clone_path))
            logger.info(f"Pulling latest on {repo.active_branch.name}...")
            try:
                repo.git.checkout("main")
            except GitCommandError:
                repo.git.checkout("master")
            repo.git.pull("origin")
            return str(clone_path)

        clone_path.parent.mkdir(parents=True, exist_ok=True)
        clone_url = f"https://x-access-token:{self.config.github.token}@github.com/{self.config.github.repo}.git"
        Repo.clone_from(clone_url, str(clone_path))
        logger.info(f"Cloned {self.config.github.repo} → {clone_path}")
        return str(clone_path)

    def create_branch(self, clone_path: str, branch_name: str) -> Repo:
        """Create and checkout a feature branch from the latest main."""
        repo = Repo(clone_path)
        default_branch = self._get_default_branch(repo)
        repo.git.checkout(default_branch)
        repo.git.pull("origin", default_branch)

        if branch_name in [b.name for b in repo.branches]:
            repo.git.checkout(branch_name)
            logger.info(f"Switched to existing branch: {branch_name}")
        else:
            repo.git.checkout("-b", branch_name)
            logger.info(f"Created branch: {branch_name}")
        return repo

    def commit_and_push(
        self, clone_path: str, branch_name: str, message: str, files: list[str] | None = None
    ) -> str:
        """Stage files, commit, push to remote. Returns commit SHA."""
        repo = Repo(clone_path)
        if files:
            for f in files:
                repo.git.add(f)
        else:
            repo.git.add("-A")

        if not repo.is_dirty(untracked_files=False) and not repo.index.diff("HEAD"):
            logger.warning("Nothing to commit")
            return repo.head.commit.hexsha

        repo.index.commit(message)
        repo.git.push("--set-upstream", "origin", branch_name)
        sha = repo.head.commit.hexsha
        logger.info(f"Pushed {sha[:8]} to origin/{branch_name}")
        return sha

    # ------------------------------------------------------------------
    # Pull Requests
    # ------------------------------------------------------------------

    def create_pull_request(
        self,
        branch_name: str,
        title: str,
        body: str,
        issue_numbers: list[int],
        labels: list[str] | None = None,
    ) -> PullRequest:
        """Create a PR from the feature branch to the default branch."""
        closes_refs = " ".join(f"Closes #{n}" for n in issue_numbers)
        full_body = f"{body}\n\n---\n{closes_refs}"

        default = self._repo.default_branch
        pr = self._repo.create_pull(
            title=title,
            body=full_body,
            head=branch_name,
            base=default,
        )

        if labels:
            pr.add_to_labels(*labels)

        logger.info(f"Created PR #{pr.number}: {pr.html_url}")
        return pr

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_default_branch(repo: Repo) -> str:
        branches = [b.name for b in repo.branches]
        for candidate in ("main", "master"):
            if candidate in branches:
                return candidate
        return branches[0] if branches else "main"
