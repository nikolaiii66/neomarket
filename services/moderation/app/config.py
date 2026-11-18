from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:////tmp/neomarket_moderation.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    service_key: str = "dev-service-key"
    b2b_base_url: str = ""
    b2b_service_key: str = "dev-mod-to-b2b-key"
    b2b_timeout_seconds: float = 3.0


settings = Settings()
