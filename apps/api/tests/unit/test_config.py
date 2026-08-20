"""Settings behaviour that guards the prod deployment: managed-platform
database URLs must be rewritten to the one installed driver, and the prod
environment must refuse to boot open or with dev secrets."""

from __future__ import annotations

import pytest

from haaland.config import Settings

_PROD_OVERRIDES = dict(
    env="prod",
    secret_key="a-real-secret",
    vault_encryption_key="c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0ISEh",  # 32B b64
    cors_origins="https://dashboard.example.com",
    api_auth_token="a-real-token",
)


def _settings(**overrides) -> Settings:
    # _env_file=None: the developer's local .env must not leak into assertions.
    return Settings(_env_file=None, **overrides)


class TestDatabaseUrlNormalisation:
    @pytest.mark.parametrize(
        "given",
        [
            "postgres://u:p@host:5432/db",  # Render/Heroku injection
            "postgresql://u:p@host:5432/db",  # would resolve to psycopg2
            "postgresql+asyncpg://u:p@host:5432/db",  # already explicit
        ],
    )
    def test_bare_schemes_become_asyncpg(self, given: str) -> None:
        settings = _settings(database_url=given)
        assert str(settings.database_url).startswith("postgresql+asyncpg://")

    def test_other_explicit_drivers_pass_through(self) -> None:
        settings = _settings(database_url="postgresql+psycopg://u:p@host:5432/db")
        assert str(settings.database_url).startswith("postgresql+psycopg://")


class TestProdFailFast:
    def test_prod_with_real_values_boots(self) -> None:
        assert _settings(**_PROD_OVERRIDES).is_prod

    @pytest.mark.parametrize(
        ("missing", "expected_fragment"),
        [
            ("secret_key", "HAALAND_SECRET_KEY"),
            ("vault_encryption_key", "HAALAND_VAULT_ENCRYPTION_KEY"),
            ("cors_origins", "HAALAND_CORS_ORIGINS"),
            ("api_auth_token", "HAALAND_API_AUTH_TOKEN"),
        ],
    )
    def test_prod_refuses_each_dev_default(self, missing: str, expected_fragment: str) -> None:
        overrides = dict(_PROD_OVERRIDES)
        del overrides[missing]  # falls back to the dev default / unset
        with pytest.raises(ValueError, match=expected_fragment):
            _settings(**overrides)

    def test_dev_allows_open_api(self) -> None:
        assert _settings(env="dev").api_auth_token is None
