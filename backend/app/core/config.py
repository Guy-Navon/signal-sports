import os


class Settings:
    app_name: str = "Signal Sports Backend"
    version: str = "0.1.0"
    debug: bool = True
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./data/signal_sports.db")


settings = Settings()
