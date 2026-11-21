import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "ActionLoop"
    app_env: str = "development"
    debug: bool = True
    port: int = 8000
    
    # Toggle for 100% zero-key operation using deterministic heuristics and fixtures
    demo_mode: bool = True
    
    # Gemini AI API
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "text-embedding-004"
    
    # Database URL
    database_url: str = "sqlite:///./actionloop.db"
    
    # Integration Adapters
    tracker_integration: str = "mock"  # mock | github | linear | trello
    github_token: Optional[str] = None
    github_repo: Optional[str] = None
    linear_api_key: Optional[str] = None
    
    # Notifier
    notifier_integration: str = "console"  # console | in_app | webhook
    slack_webhook_url: Optional[str] = None
    
    # Confirmation Gate Controls
    dry_run: bool = False
    strict_confirmation: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

settings = Settings()
