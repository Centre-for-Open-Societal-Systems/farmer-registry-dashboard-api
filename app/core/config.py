from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    PROJECT_NAME: str = "Farmer Registry Dashboard API"
    DATABASE_URL: str
    API_V1_STR: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    # National count of administrative units per level, for coverage rates. It is
    # deployment data (the registry only knows the units it has farmers in), so it
    # is configured rather than derived. Keys: regions, zones, woredas, kebeles.
    # A level left out is reported as null.
    GEO_LEVEL_TOTALS: dict[str, int] = {}


settings = Settings()
