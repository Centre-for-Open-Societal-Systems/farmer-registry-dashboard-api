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
| `GEO_LEVELS_RECHECK_SECONDS` | no | `300` | How long a detected level mapping is trusted before `fr_rpt_geo_levels` is read again. A registry that rebuilds its views with a different hierarchy is followed within this time, without a restart. Ignored when `GEO_TOP_LEVEL` is set |
| `AUTH_IAM_URL` | recommended | — | Base URL of the registry's IAM, normally its in-namespace Service, for example `http://commons-services-iam-staff-portal-api-pub`. Every Keycloak realm IAM's login providers sign staff in with becomes a trusted token issuer. With `AUTH_ISSUER` also unset, authentication is **off** (see [Security](security.md#authentication)) |
| `AUTH_ISSUER` | no | — | Explicit trusted issuers: Keycloak realm URLs, comma-separated, for example `https://keycloak.example.org/realms/staff`. Each must equal the tokens' `iss` exactly. Combines with `AUTH_IAM_URL` |
| `AUTH_IAM_REFRESH_SECONDS` | no | `600` | How often IAM's login providers are read again. A token from an unknown issuer also triggers a re-read, at most once a minute |
| `AUTH_JWKS_URL` | no | `<issuer>/protocol/openid-connect/certs` | Signing keys for a single `AUTH_ISSUER`, when this service reaches Keycloak by another address than the issuer's |
| `AUTH_AUDIENCE` | no | `farmer-registry-dashboard-api` | This service's Keycloak client. Tokens must name it in `aud` |
| `AUTH_ROLE` | no | `charts:read` | Client role on `AUTH_AUDIENCE` a caller must hold |
| `AUTH_LEEWAY_SECONDS` | no | `30` | Clock skew tolerated when checking token times |
| `PROJECT_NAME` | no | `Farmer Registry Dashboard API` | Title shown in the OpenAPI docs |

Example `.env`:

```ini
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/farmer_registry_db
ALLOWED_ORIGINS=["http://localhost:3000"]
GEO_LEVEL_TOTALS={"woredas": 1138}
```

## Keycloak setup

Authentication needs, in the registry's realm:

1. **This service's client**, `AUTH_AUDIENCE`: confidential, with every flow off (it never signs
   anyone in). It only holds the role.
2. **Its client role** `AUTH_ROLE`.
3. **That role on the caller's service account**: the dashboard's own client, with service accounts
   enabled.

Keycloak then puts `AUTH_AUDIENCE` in `aud` and the role in `resource_access` of the caller's
client-credentials tokens by itself (the realm's default `roles` scope), so no mapper is needed.

The farmer dashboard's deploy job creates all three when its dashboard-api authentication is on, so
normally nothing is done by hand. Manually, with `kcadm.sh`:

```bash
kcadm.sh create clients -r farmer -s clientId=farmer-registry-dashboard-api -s publicClient=false \
  -s standardFlowEnabled=false -s directAccessGrantsEnabled=false -s serviceAccountsEnabled=false
kcadm.sh create clients/<id>/roles -r farmer -s name=charts:read
kcadm.sh add-roles -r farmer --uusername service-account-farmer-registry-dashboard \
  --cclientid farmer-registry-dashboard-api --rolename charts:read
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
