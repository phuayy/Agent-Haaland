"""GitHub credential strategies. Two modes:

- `pat`  — a personal access token from the environment. Fast to set up,
  fine for a single developer, but it is a user-scoped, long-lived secret.
- `app`  — a GitHub App installation (docs/02's target). The App holds a
  private key; short-lived installation tokens (~1h) are minted on demand
  and auto-refreshed. Least-privilege, revocable per repository, and the
  App's permission set physically excludes merge — which is the product's
  core safety claim (docs/09).

Both expose the same two capabilities the rest of the codebase needs:
an auth strategy for the githubkit REST client, and a bearer token usable
in an HTTPS clone URL. Nothing outside this module knows which mode is
active."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from githubkit import AppAuthStrategy, GitHub, TokenAuthStrategy, UnauthAuthStrategy

from haaland.config import Settings

_TOKEN_REFRESH_MARGIN_SECONDS = 300


class GitHubCredentials(Protocol):
    def auth_strategy(self): ...
    async def clone_token(self) -> str | None:
        """Bearer token to embed in an HTTPS clone URL, or None for
        anonymous access (public repos only)."""
        ...


class AnonymousCredentials:
    def auth_strategy(self):
        return UnauthAuthStrategy()

    async def clone_token(self) -> str | None:
        return None


@dataclass
class PatCredentials:
    token: str

    def auth_strategy(self):
        return TokenAuthStrategy(self.token)

    async def clone_token(self) -> str | None:
        return self.token


@dataclass
class AppCredentials:
    app_id: str
    private_key: str
    installation_id: int
    _cached_token: str | None = field(default=None, repr=False)
    _cached_expiry: float = field(default=0.0, repr=False)

    def auth_strategy(self):
        # githubkit's installation strategy handles the JWT -> installation
        # token exchange and refresh internally for every REST call.
        return AppAuthStrategy(self.app_id, self.private_key).as_installation(self.installation_id)

    async def clone_token(self) -> str | None:
        """git itself can't speak the App JWT flow, so clones need a minted
        installation access token. Cached until shortly before its ~1h
        expiry — one mint covers many clones."""
        now = time.time()
        if self._cached_token and now < self._cached_expiry - _TOKEN_REFRESH_MARGIN_SECONDS:
            return self._cached_token

        app_client = GitHub(AppAuthStrategy(self.app_id, self.private_key))
        resp = await app_client.rest.apps.async_create_installation_access_token(
            self.installation_id
        )
        data = resp.parsed_data
        self._cached_token = data.token
        self._cached_expiry = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00")).timestamp()
        return self._cached_token


def build_credentials(settings: Settings) -> GitHubCredentials:
    if settings.github_auth_mode == "app":
        private_key = settings.github_app_private_key
        if settings.github_app_private_key_path:
            private_key = settings.github_app_private_key_path.read_text(encoding="utf-8")
        if not (settings.github_app_id and private_key and settings.github_app_installation_id):
            raise RuntimeError(
                "github_auth_mode=app requires HAALAND_GITHUB_APP_ID, "
                "HAALAND_GITHUB_APP_PRIVATE_KEY (or _PATH), and "
                "HAALAND_GITHUB_APP_INSTALLATION_ID"
            )
        return AppCredentials(
            app_id=settings.github_app_id,
            private_key=private_key,
            installation_id=settings.github_app_installation_id,
        )
    if settings.github_token:
        return PatCredentials(settings.github_token)
    return AnonymousCredentials()
