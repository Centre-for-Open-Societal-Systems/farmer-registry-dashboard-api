from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    PROJECT_NAME: str = "Farmer Registry Dashboard API"
    # libpq-style DSN. The password may be left out and supplied as PGPASSWORD,
    # which avoids URL-encoding it.
    DATABASE_URL: str
    PGPASSWORD: str | None = None
    # Connections per worker process. The registry database is shared with the
    # rest of the platform and the dashboards cache responses, so the pool stays
    # small; asyncpg's own default holds 10 open per worker.
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 5
    API_V1_STR: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    # National count of administrative units per level, for coverage rates. It is
    # deployment data (the registry only knows the units it has farmers in), so it
    # is configured rather than derived. Keys: regions, zones, woredas, kebeles.
    # A level left out is reported as null.
    GEO_LEVEL_TOTALS: dict[str, int] = {}
    # Reporting-view position (1-2) of the dashboards' first geography level, the
    # region. Unset: derived from fr_rpt_geo_levels, skipping a country root
    # (see app/core/geo.py). Set it only to override that.
    GEO_TOP_LEVEL: int | None = None


settings = Settings()
