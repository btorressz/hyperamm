from __future__ import annotations

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    redstone_stale_after_seconds: float = 5.0

    kraken_reference_enabled: bool = False
    kraken_symbol: str | None = None
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    kraken_stale_after_seconds: float = 5.0

    coingecko_reference_enabled: bool = False
    coingecko_api_key: str | None = Field(default=None, repr=False)
    coingecko_coin_id: str | None = None
    coingecko_api_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_poll_interval_seconds: float = 20.0
    coingecko_stale_after_seconds: float = 90.0

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
