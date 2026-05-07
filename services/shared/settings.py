"""Centralised settings — every service imports from here."""
from __future__ import annotations

import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Database ----
    db_host: str = Field("db.magedzamzam.ae", alias="DB_HOST")
    db_port: int = Field(5432, alias="DB_PORT")
    db_name: str = Field("beacon", alias="DB_NAME")
    db_user: str = Field("magedzamzam", alias="DB_USER")
    db_password: str = Field("", alias="DB_PASSWORD")

    # ---- Auth ----
    jwt_secret: str = Field("change-me-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # ---- Scraper ----
    scraper_base_url: str = Field("https://stockanalysis.com", alias="SCRAPER_BASE_URL")
    scraper_user_agent: str = Field(
        "Mozilla/5.0 (compatible; BeaconScreener/1.0; +https://github.com/)",
        alias="SCRAPER_USER_AGENT",
    )
    scraper_request_delay_sec: float = Field(1.5, alias="SCRAPER_DELAY_SEC")
    scraper_concurrency: int = Field(4, alias="SCRAPER_CONCURRENCY")
    scraper_timeout_sec: int = Field(30, alias="SCRAPER_TIMEOUT")

    # ---- Scheduler ----
    daily_scrape_cron: str = Field("0 11 * * *", alias="DAILY_SCRAPE_CRON")
    timezone: str = Field("Asia/Dubai", alias="TZ")

    # ---- API ----
    api_cors_origins: str = Field("*", alias="API_CORS_ORIGINS")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        # Same driver (psycopg v3 / "psycopg" package) but used in sync mode by SQLAlchemy.
        # Without the +psycopg suffix, SQLAlchemy defaults to psycopg2 which we don't install.
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
