import os


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name: str = "Signal Sports Backend"
    version: str = "0.1.0"
    debug: bool = True
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./data/signal_sports.db")
    auth_cookie_name: str = os.environ.get("AUTH_COOKIE_NAME", "signal_session")
    auth_cookie_secure: bool = env_bool("AUTH_COOKIE_SECURE", False)
    csrf_allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.environ.get(
            "CSRF_ALLOWED_ORIGINS",
            ",".join(
                [
                    "http://localhost:5173",
                    "http://localhost:5174",
                    "http://localhost:5175",
                    "http://127.0.0.1:5173",
                    "http://127.0.0.1:5174",
                    "http://127.0.0.1:5175",
                    "http://localhost:8000",
                    "http://127.0.0.1:8000",
                    "http://testserver",
                ]
            ),
        ).split(",")
        if origin.strip()
    )


settings = Settings()
