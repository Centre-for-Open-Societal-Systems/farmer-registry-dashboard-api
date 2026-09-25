# Configuration

Never commit real values: `.env` is git-ignored, `.env.example` holds placeholders only, and deployed
environments take values from the platform's secret store.

Settings are read from environment variables, or from a `.env` file in the working directory, by
`app/core/config.py` (pydantic-settings). Complex values are JSON.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | — | PostgreSQL DSN for the farmer registry database, for example `postgresql://dashboard_ro@postgres:5432/farmer_registry_db`. The service fails to start without it |
| `PGPASSWORD` | recommended | — | Database password, read by asyncpg when the DSN has none. Keeping it out of `DATABASE_URL` avoids URL-encoding it, and a password with `@ : / ? #` then just works. A password inside the DSN also works, but must be URL-encoded |
| `DB_POOL_MIN_SIZE` | no | `1` | Connections each worker keeps open |
| `DB_POOL_MAX_SIZE` | no | `5` | Most connections each worker opens under load |
| `API_V1_STR` | no | `/api/v1` | Route prefix for the chart endpoints |
| `ALLOWED_ORIGINS` | no | `["http://localhost:3000"]` | JSON list of origins allowed by CORS. Browsers are not expected to call the API directly, so keep this narrow |
| `GEO_LEVEL_TOTALS` | no | `{}` | JSON object giving the national number of administrative units per level, used by `registryCoverage`. Keys: `regions`, `zones`, `woredas`, `kebeles`. A missing level is reported as `null` |
| `GEO_TOP_LEVEL` | no | detected | Reporting-view position (`1` or `2`) of the region level. Normally leave it unset: the API reads `fr_rpt_geo_levels` and skips a country root. Set it only if the level names are unusual, for example a root that is not called `country` |
| `PROJECT_NAME` | no | `Farmer Registry Dashboard API` | Title shown in the OpenAPI docs |

Example `.env`:

```ini
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/farmer_registry_db
ALLOWED_ORIGINS=["http://localhost:3000"]
GEO_LEVEL_TOTALS={"woredas": 1138}
```

## Database account

The service only reads, so give it a dedicated read-only role:

```sql
CREATE ROLE dashboard_ro LOGIN PASSWORD '…';
GRANT CONNECT ON DATABASE farmer_registry_db TO dashboard_ro;
GRANT USAGE ON SCHEMA public TO dashboard_ro;
GRANT SELECT ON fr_rpt_farmer, fr_rpt_land TO dashboard_ro;
```

This is enough for every endpoint. `GET /health` only needs the ability to connect.

## Server process

The container runs:

```
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

To change the worker count, override the container command. Each worker opens its own connection
pool of `DB_POOL_MIN_SIZE`–`DB_POOL_MAX_SIZE` connections (1–5 by default). See
[Deployment and operations](deployment.md#sizing) for sizing.

## Test settings

| Variable | Default | Description |
| --- | --- | --- |
| `TEST_DATABASE_URL` | none | Server the database tests connect to, with a role that may create schemas. The tests create and drop their own schema and never read registry data. When unset, database tests are skipped and only the unit tests run |
