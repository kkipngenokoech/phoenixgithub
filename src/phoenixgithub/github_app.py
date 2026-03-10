"""GitHub App authentication — JWT signing and installation token management."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import jwt
from github import Github, GithubIntegration

logger = logging.getLogger(__name__)

# Installation tokens are valid for 1 hour; refresh with a 5-minute buffer.
_TOKEN_REFRESH_BUFFER_SECONDS = 300


@dataclass
class InstallationToken:
    """Cached installation token with expiry tracking."""

    token: str
    expires_at: float  # Unix timestamp
    installation_id: int

    @property
    def is_expired(self) -> bool:
        return time.time() >= (self.expires_at - _TOKEN_REFRESH_BUFFER_SECONDS)


class GitHubAppAuth:
    """Manages GitHub App authentication: JWT signing → installation tokens.

    Usage::

        app_auth = GitHubAppAuth(app_id=12345, private_key_path="key.pem")

        # Get a PyGithub instance scoped to a specific installation
        gh = app_auth.get_github_for_installation(installation_id)

        # Get a raw access token (e.g. for git clone URLs)
        token = app_auth.get_access_token(installation_id)
    """

    def __init__(self, app_id: int, private_key: str) -> None:
        self.app_id = app_id
        self._private_key = private_key
        self._integration = GithubIntegration(
            integration_id=app_id,
            private_key=private_key,
        )
        self._token_cache: dict[int, InstallationToken] = {}

    @classmethod
    def from_key_file(cls, app_id: int, private_key_path: str) -> GitHubAppAuth:
        """Create from a PEM key file path."""
        key_text = Path(private_key_path).read_text()
        return cls(app_id=app_id, private_key=key_text)

    def _create_jwt(self) -> str:
        """Create a short-lived JWT for authenticating as the GitHub App."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Clock drift allowance
            "exp": now + (10 * 60),  # 10 minute max
            "iss": self.app_id,
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def get_access_token(self, installation_id: int) -> str:
        """Get a valid installation access token, refreshing if expired."""
        cached = self._token_cache.get(installation_id)
        if cached and not cached.is_expired:
            return cached.token

        token_obj = self._integration.get_access_token(installation_id)
        inst_token = InstallationToken(
            token=token_obj.token,
            expires_at=token_obj.expires_at.timestamp(),
            installation_id=installation_id,
        )
        self._token_cache[installation_id] = inst_token
        logger.info(
            f"Refreshed installation token for installation {installation_id} "
            f"(expires {token_obj.expires_at.isoformat()})"
        )
        return inst_token.token

    def get_github_for_installation(self, installation_id: int) -> Github:
        """Return a PyGithub client authenticated as a specific installation."""
        token = self.get_access_token(installation_id)
        return Github(token)

    def get_installation_id_for_repo(self, owner: str, repo_name: str) -> int | None:
        """Look up the installation ID for a given repo."""
        try:
            installation = self._integration.get_repo_installation(owner, repo_name)
            return installation.id
        except Exception:
            logger.warning(f"No installation found for {owner}/{repo_name}")
            return None

    def list_installations(self) -> list[dict]:
        """List all installations of this GitHub App."""
        installations = self._integration.get_installations()
        return [
            {
                "id": inst.id,
                "account": inst.raw_data.get("account", {}).get("login", "unknown"),
                "target_type": inst.raw_data.get("target_type", "unknown"),
            }
            for inst in installations
        ]
