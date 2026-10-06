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
    # Seconds a detected top level is trusted before fr_rpt_geo_levels is read
    # again, so a rebuilt hierarchy is picked up without a restart.
    GEO_LEVELS_RECHECK_SECONDS: int = 300
    # Service-to-service authentication of chart requests (app/core/auth.py).
    # Trusted token issuers: the realms behind the login providers of the
    # registry's IAM (its base URL, normally the in-namespace Service), and/or
    # explicit Keycloak realm URLs, comma-separated. Both unset or empty turn
    # authentication off, which is only safe while the network keeps every
    # other client out.
    AUTH_IAM_URL: str | None = None
    AUTH_ISSUER: str | None = None
    # How often IAM's login providers are read again.
    AUTH_IAM_REFRESH_SECONDS: int = 600
    # Where the signing keys are published, for a single AUTH_ISSUER only.
    # Unset: <issuer>/protocol/openid-connect/certs (Keycloak).
    AUTH_JWKS_URL: str | None = None
    # This service's Keycloak client, and the client role a caller must hold.
    AUTH_AUDIENCE: str = "farmer-registry-dashboard-api"
    AUTH_ROLE: str = "charts:read"
    # Clock skew tolerated on exp/iat/nbf.
    AUTH_LEEWAY_SECONDS: int = 30


settings = Settings()
