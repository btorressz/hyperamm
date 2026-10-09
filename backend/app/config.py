from __future__ import annotations

from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Trusted local operator input. Never included in agent/public snapshots.
    predictive_model_artifact_path: str | None = Field(default=None, repr=False, exclude=True)
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", case_sensitive=False)

    app_name: str = "HyperAMM"
    api_prefix: str = "/api/v1"
    market: str = "ETH"
    market_data_mode: str = "DEMO"
    execution_mode: str = "PAPER"
    market_stale_after_seconds: float = 5.0
    demo_update_interval_seconds: float = 1.0
    enable_hyperliquid_testnet_orders: bool = False
    hyperliquid_private_key: str | None = Field(default=None, repr=False)
    hyperliquid_account_address: str | None = None
    hyperliquid_testnet_url: str = "https://api.hyperliquid-testnet.xyz"

    reference_firewall_enabled: bool = True
    redstone_enabled: bool = False
    redstone_api_key: str | None = Field(default=None, repr=False)
    redstone_data_service_id: str = "redstone-primary-prod"
    redstone_feed_id: str | None = None
    redstone_live_ws_url: str | None = None
    redstone_stale_after_seconds: float = Field(default=5.0, gt=0, le=300)
    redstone_public_http_fallback_enabled: bool = True
    redstone_public_http_url: str = "https://api.redstone.finance/prices"
    redstone_public_http_provider: str = "redstone"
    redstone_public_http_symbol: str | None = None
    redstone_public_http_poll_interval_seconds: float = Field(default=10.0, ge=5, le=3600)
    redstone_public_http_stale_after_seconds: float = Field(default=30.0, gt=0, le=3600)

    kraken_reference_enabled: bool = False
    kraken_symbol: str | None = None
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    kraken_stale_after_seconds: float = Field(default=5.0, gt=0, le=300)

    coingecko_reference_enabled: bool = False
    coingecko_api_key: str | None = Field(default=None, repr=False)
    coingecko_coin_id: str | None = None
    coingecko_api_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_poll_interval_seconds: float = Field(default=20.0, gt=0, le=3600)
    coingecko_stale_after_seconds: float = Field(default=90.0, gt=0, le=3600)

    yfinance_reference_enabled: bool = False
    yfinance_symbol: str = "ETH-USD"
    yfinance_stale_after_seconds: float = Field(default=30, gt=0, le=300)

    cors_origins: str = "http://localhost:5173"

    redis_enabled: bool = False
    redis_required: bool = False
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", repr=False)
    redis_namespace: str = Field(default="hyperamm", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    redis_terminal_channel: str = Field(default="terminal", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    redis_default_ttl_seconds: int = Field(default=30, ge=10, le=300)
    redis_worker_heartbeat_ttl_seconds: int = Field(default=15, ge=10, le=300)
    redis_operation_timeout_seconds: float = Field(default=1, gt=0, le=5)
    redis_research_enabled: bool = False

    @model_validator(mode="after")
    def redis_options(self):
        from urllib.parse import urlsplit
        if (self.redis_required or self.redis_research_enabled) and not self.redis_enabled:
            raise ValueError("Redis required/research modes require redis_enabled")
        if self.redis_enabled and urlsplit(self.redis_url).scheme not in {"redis", "rediss"}:
            raise ValueError("Redis URL must use redis or rediss")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
