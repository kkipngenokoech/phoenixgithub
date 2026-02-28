"""Configuration — all settings from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class GitHubConfig(BaseModel):
    token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    repo: str = Field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))  # owner/repo
    poll_interval: int = Field(default_factory=lambda: int(os.getenv("POLL_INTERVAL", "60")))
    max_concurrent_runs: int = Field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_RUNS", "2")))

    @property
    def owner(self) -> str:
        return self.repo.split("/")[0] if "/" in self.repo else ""

    @property
    def repo_name(self) -> str:
        return self.repo.split("/")[1] if "/" in self.repo else self.repo


class LabelConfig(BaseModel):
    """GitHub labels used as state machine transitions."""
    ready: str = "ai:ready"
    in_progress: str = "ai:in-progress"
    review: str = "ai:review"
    revise: str = "ai:revise"
    done: str = "ai:done"
    failed: str = "ai:failed"


class LLMConfig(BaseModel):
    provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic"))
    model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"))
    api_key: str = Field(default_factory=lambda: os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY", ""))
    base_url: str | None = Field(default_factory=lambda: os.getenv("LLM_BASE_URL"))
    temperature: float = 0.2
    max_tokens: int = 8192


class AgentConfig(BaseModel):
    max_retries: int = 2
    test_command: str = Field(default_factory=lambda: os.getenv("TEST_COMMAND", "pytest"))
    build_command: str = Field(default_factory=lambda: os.getenv("BUILD_COMMAND", ""))


class Config(BaseModel):
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    labels: LabelConfig = Field(default_factory=LabelConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    workspace_dir: str = Field(
        default_factory=lambda: os.getenv("WORKSPACE_DIR", str(Path.cwd() / "workspace"))
    )
    state_file: str = Field(
        default_factory=lambda: os.getenv("STATE_FILE", str(Path.cwd() / ".watcher-state.json"))
    )
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @classmethod
    def from_env(cls) -> Config:
        return cls()
