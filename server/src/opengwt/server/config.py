"""Settings in three layers: code defaults, an optional YAML file named by ``OPENGWT_CONFIG``,
and ``OPENGWT_``-prefixed environment variables; later layers win (ADR 0004)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

CONFIG_ENV = "OPENGWT_CONFIG"
MEMORY_SCHEME = "memory://"
DEFAULT_SECRET = "dev-only-secret-change-me-before-any-deployment"


class ConfigError(ValueError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENGWT_", env_nested_delimiter="__", extra="ignore"
    )

    env: str = "dev"
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1
    log_level: str = "INFO"

    data_dir: Path | None = None

    database_url: str = "sqlite+aiosqlite:///./opengwt.db"
    cache_url: str = MEMORY_SCHEME
    match_store_url: str = MEMORY_SCHEME
    event_bus_url: str = MEMORY_SCHEME
    tasks: str = "inline"
    auto_migrate: bool = True

    auth_secret: str = DEFAULT_SECRET
    token_ttl_seconds: int = 60 * 60 * 24 * 30

    bot: str = "greedy"
    turn_timeout_seconds: float = 0
    room_code_length: int = 6
    event_history: int = 2000

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        path = os.environ.get(CONFIG_ENV)
        if path:
            sources.append(
                YamlConfigSettingsSource(settings_cls, yaml_file=path, yaml_file_encoding="utf-8")
            )
        return tuple(sources)

    def resolved_data_dir(self) -> Path:
        if self.data_dir is not None:
            return self.data_dir
        for candidate in (Path("data"), Path("..") / "data"):
            if (candidate / "cards").is_dir():
                return candidate
        raise ConfigError("cannot find the data/ directory; set OPENGWT_DATA_DIR")

    @property
    def shared_backends(self) -> bool:
        return not (
            self.match_store_url.startswith(MEMORY_SCHEME)
            or self.event_bus_url.startswith(MEMORY_SCHEME)
        )

    def validate_deployment(self) -> None:
        """Refuse a configuration that would run incorrectly (ADR 0004, ADR 0008)."""
        if self.workers > 1 and not self.shared_backends:
            raise ConfigError(
                "more than one worker needs a shared match store and event bus "
                "(OPENGWT_MATCH_STORE_URL and OPENGWT_EVENT_BUS_URL); memory backends hold live "
                "matches in one process"
            )
        if self.env != "dev" and self.auth_secret == DEFAULT_SECRET:
            raise ConfigError("set OPENGWT_AUTH_SECRET outside the dev environment")
        if self.tasks != "inline":
            raise ConfigError("only the inline task runner exists yet")
