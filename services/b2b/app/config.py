from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:////tmp/neomarket_b2b.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    service_keys: dict[str, str] = {
        "moderation": "moderation-service-key",
        "b2c": "b2c-service-key",
    }


settings = Settings()
