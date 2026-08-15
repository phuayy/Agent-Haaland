from __future__ import annotations

import pytest
from githubkit import TokenAuthStrategy, UnauthAuthStrategy

from haaland.config import Settings
from haaland.integrations.scm.auth import (
    AnonymousCredentials,
    AppCredentials,
    PatCredentials,
    build_credentials,
)


def test_pat_mode_with_token():
    creds = build_credentials(Settings(github_auth_mode="pat", github_token="ghp_x"))
    assert isinstance(creds, PatCredentials)
    assert isinstance(creds.auth_strategy(), TokenAuthStrategy)


async def test_pat_clone_token_is_the_token_itself():
    assert await PatCredentials("ghp_x").clone_token() == "ghp_x"


def test_pat_mode_without_token_falls_back_to_anonymous():
    creds = build_credentials(Settings(github_auth_mode="pat", github_token=None))
    assert isinstance(creds, AnonymousCredentials)
    assert isinstance(creds.auth_strategy(), UnauthAuthStrategy)


def test_app_mode_requires_all_three_values():
    with pytest.raises(RuntimeError, match="github_auth_mode=app requires"):
        build_credentials(Settings(github_auth_mode="app", github_app_id="123"))


def test_app_mode_builds_app_credentials():
    creds = build_credentials(
        Settings(
            github_auth_mode="app",
            github_app_id="123",
            github_app_private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            github_app_installation_id=456,
        )
    )
    assert isinstance(creds, AppCredentials)
    assert creds.installation_id == 456


def test_prod_refuses_dev_secrets():
    with pytest.raises(ValueError, match="refusing to start in prod"):
        Settings(env="prod")
