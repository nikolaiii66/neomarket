from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:////tmp/neomarket_b2c.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    b2b_base_url: str = "http://localhost:8001"
    b2b_service_key: str = "b2c-service-key"


settings = Settings()
