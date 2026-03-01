#!/usr/bin/env python3
"""Create required PhoenixGitHub labels in the configured repository."""

from __future__ import annotations

import sys
from pathlib import Path

from github import GithubException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phoenixgithub.config import Config
from phoenixgithub.github_client import GitHubClient


def main() -> int:
    config = Config.from_env()
    if not config.github.token:
        print("Missing GITHUB_TOKEN in environment/.env", file=sys.stderr)
        return 1
    if not config.github.repo or "/" not in config.github.repo:
        print("Missing or invalid GITHUB_REPO (expected owner/repo)", file=sys.stderr)
        return 1

    try:
        client = GitHubClient(config)
        client.ensure_labels()
    except GithubException as exc:
        print(f"GitHub API error: {exc}", file=sys.stderr)
        return 1

    print(f"Labels ensured for {config.github.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
