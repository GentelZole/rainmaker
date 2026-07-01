"""RainMaker Configuration"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # Africa's Talking
    at_username: str = "sandbox"
    at_api_key: str = ""

    # Cardano / Blockfrost (Preprod Testnet)
    blockfrost_project_id: str = ""
    cardano_network: str = "preprod"  # preprod | mainnet

    # App
    secret_key: str = "change-me-in-production"
    database_url: str = "sqlite+aiosqlite:///./rainmaker.db"
    db_passphrase: str = ""  # Set for SQLCipher encryption at rest
    ussd_short_code: str = "*384*225533#"

    # Wallet
    pin_min_length: int = 4
    pin_max_attempts: int = 5
    pin_lockout_minutes: int = 1440  # 24h

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()