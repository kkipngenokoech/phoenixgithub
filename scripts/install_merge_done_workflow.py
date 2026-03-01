#!/usr/bin/env python3
"""Install/update a GitHub Actions workflow that marks merged issues as ai:done."""

from __future__ import annotations

import sys
from pathlib import Path

from github import Github, GithubException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phoenixgithub.config import Config


WORKFLOW_PATH = ".github/workflows/phoenix-mark-done.yml"


def _workflow_content(review_label: str, done_label: str) -> str:
    return f"""name: Phoenix - Mark Issue Done On Merge

on:
  pull_request:
    types: [closed]

permissions:
  issues: write
  pull-requests: read
  contents: read

jobs:
  mark-done:
    if: ${{{{ github.event.pull_request.merged == true }}}}
    runs-on: ubuntu-latest
    steps:
      - name: Move linked issues to done
        uses: actions/github-script@v7
        with:
          script: |
            const pr = context.payload.pull_request;
            const body = pr.body || "";
            const regex = /\\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\\s+#(\\d+)\\b/gi;
            const issueNumbers = new Set();
            let match;

            while ((match = regex.exec(body)) !== null) {{
              issueNumbers.add(Number(match[1]));
            }}

            if (issueNumbers.size === 0) {{
              core.info("No linked issues found in PR body.");
              return;
            }}

            for (const issue_number of issueNumbers) {{
              core.info(`Updating labels for issue #${{issue_number}}`);

              try {{
                await github.rest.issues.removeLabel({{
                  owner: context.repo.owner,
                  repo: context.repo.repo,
                  issue_number,
                  name: "{review_label}",
                }});
              }} catch (err) {{
                core.info(`No '{review_label}' label to remove on #${{issue_number}} (or already removed).`);
              }}

              await github.rest.issues.addLabels({{
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number,
                labels: ["{done_label}"],
              }});
            }}
"""


def main() -> int:
    config = Config.from_env()
    if not config.github.token:
        print("Missing GITHUB_TOKEN in environment/.env", file=sys.stderr)
        return 1
    if not config.github.repo or "/" not in config.github.repo:
        print("Missing or invalid GITHUB_REPO (expected owner/repo)", file=sys.stderr)
        return 1

    gh = Github(config.github.token)
    try:
        repo = gh.get_repo(config.github.repo)
        branch = repo.default_branch
        content = _workflow_content(config.labels.review, config.labels.done)

        try:
            existing = repo.get_contents(WORKFLOW_PATH, ref=branch)
            repo.update_file(
                path=WORKFLOW_PATH,
                message="ci: configure merged PR issue label automation",
                content=content,
                sha=existing.sha,
                branch=branch,
            )
            print(f"Updated {WORKFLOW_PATH} in {config.github.repo}@{branch}")
        except GithubException as exc:
            if exc.status != 404:
                raise
            repo.create_file(
                path=WORKFLOW_PATH,
                message="ci: configure merged PR issue label automation",
                content=content,
                branch=branch,
            )
            print(f"Created {WORKFLOW_PATH} in {config.github.repo}@{branch}")
    except GithubException as exc:
        print(f"GitHub API error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
