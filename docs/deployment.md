> Authentication is required by default. The owning registry Helm chart supplies
> `AUTH_ENABLED=true` and `AUTH_IAM_URL` (or `AUTH_ISSUER`). Missing trust stops startup;
> requests also fail closed if configuration is invalid. `AUTH_ENABLED=false` is an
> explicit opt-out for isolated local development only, never for a registry deployment.
> Build, deployment and environment configuration belong to the owning registry CI/Helm.

# Deployment and operations

## Container image

The `Dockerfile` builds a two-stage `python:3.11-slim` image:

1. **Builder:** builds wheels for `requirements.txt`.
2. **Runtime:** installs the wheels, copies `app/`, and runs gunicorn with four Uvicorn workers on
   port `8000`.

The image declares a `HEALTHCHECK` that calls `GET /health` every 30 seconds. `/health` runs
`SELECT 1`, so the container also reports unhealthy when the database is unreachable.

```bash
docker build -t farmer-registry-dashboard-api:<version> .
docker run -d --name farmer-registry-dashboard-api \
  -e DATABASE_URL=postgresql://dashboard_ro@postgres:5432/farmer_registry_db \n  -e PGPASSWORD=*** \
  -e GEO_LEVEL_TOTALS='{"woredas": 1138}' \
  -p 127.0.0.1:8005:8000 \
  farmer-registry-dashboard-api:<version>
```

## Docker Compose

`docker-compose.yml` runs the service alone, publishing port `8005` on `127.0.0.1` only. It requires
`DATABASE_URL` from the environment or an uncommitted `.env`, and refuses to start without it. To run it next to the farmer registry stack, add it to
the same Docker network and use the Postgres service name in `DATABASE_URL`.

## Kubernetes

The service is stateless and fits a standard Deployment and Service pair:

- **Service:** `ClusterIP` only. Do not create a public Ingress: the only client is the
  dashboards BFF (see [Security](security.md#network-exposure)).
- **Probes:** a readiness and liveness probe on `GET /health`, port `8000`.
- **Secrets:** `PGPASSWORD` from a Secret, `DATABASE_URL` without the password; `GEO_LEVEL_TOTALS` and `ALLOWED_ORIGINS` from a
  ConfigMap.
- **Resources:** a starting point is `100m` / `256Mi` requested per replica. The work is I/O-bound.

## Authentication rollout

The owning registry pipeline builds this image together with its dashboard UI.
Registry Helm owns `dashboardApi.auth`: enable it and configure a trusted issuer
or IAM URL there. The template emits AUTH_ENABLED, AUTH_ISSUER/AUTH_IAM_URL,
AUTH_AUDIENCE and AUTH_ROLE; reserved auth settings must not also be placed in
`dashboardApi.env`. Missing trust fails closed. AUTH_ENABLED=false is local only.

The registry-owned UI Helm chart provisions the service client/role and IAM tile,
then checks anonymous/invalid-token 401 responses and real authenticated charts.
The browser still requires its own IAM session and viewer role. Do not promote
an older API image that ignores these settings, or disable staging/ownership gates
to make a rollout pass. No secret value belongs in an image or committed values.

## Sizing

- **Connections:** each gunicorn worker holds its own asyncpg pool of `DB_POOL_MIN_SIZE` to
  `DB_POOL_MAX_SIZE` connections (1–5 by default). One replica therefore keeps **workers × 1** open
  and uses at most **workers × 5** (20 with 4 workers). The database is shared with the rest of the
  registry, so keep the pool small. The BFF cache means a handful of connections serves any number
  of viewers. For most deployments one replica with 2–4 workers is plenty.
- **Load:** the dashboards BFF caches every chart and filter combination (15 minutes by default) and
  warms the unfiltered view on a timer. Steady-state load is therefore roughly *one request per chart
  per distinct filter combination per cache period for each BFF instance*. It does not grow with page
  views.
- **Query cost:** each request is one aggregate over an indexed materialized view.

## Data freshness

A figure in the dashboards can lag the register by at most:

- **the view refresh interval** (hourly by default, owned by the farmer registry), plus
- **the BFF cache TTL** (15 minutes by default)

After a bulk import, refresh the views (land first, then farmer) to publish the new data.

## Monitoring

| Signal | Where | Healthy |
| --- | --- | --- |
| Container health | Docker / Kubernetes probe on `/health` | `healthy` / ready |
| Error rate | gunicorn logs (stdout) | No `500` responses |
| Latency | the BFF's `executionTime` for a cache miss | Well under 1 s |
| Database connections | `pg_stat_activity` filtered by the service's user | ≤ workers × `DB_POOL_MAX_SIZE` per replica |
| View freshness | the registry's refresh job | Last successful run within the schedule |

gunicorn does not write access logs by default. Add `--access-logfile -` to the command if you need
per-request logs.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Every chart answers `401` | The caller sends no token, or its token's `iss` is not a trusted issuer: not a realm of IAM's login providers, nor in `AUTH_ISSUER` | Turn on client-credentials in the dashboard. Compare the token's `iss` with the issuers in IAM's `login_providers` |
| Every chart answers `403` | The caller's service account lacks `AUTH_ROLE` on `AUTH_AUDIENCE` | Grant the role ([Keycloak setup](configuration.md#keycloak-setup)) |
| Every chart answers `503` | The service cannot read IAM (`AUTH_IAM_URL`) before it knows any issuer, or cannot fetch an issuer's signing keys | Check DNS, network and TLS from the container to IAM and to Keycloak. The log names which |
| Container restarts, and the log says `DATABASE_URL` is missing | Required setting absent | Set `DATABASE_URL` |
| `/health` returns 500 or the container is `unhealthy` | Database unreachable, wrong credentials, or pool exhausted | Check network and DNS to Postgres, credentials, and `pg_stat_activity` |
| A chart returns 500 with `relation "fr_rpt_farmer" does not exist` | The reporting views have not been created in this database | Run the registry's reporting-view seed and refresh |
| All counts are 0 | Filters match nothing (for example a `recordState` that does not exist), or the views are empty | Retry without filters, then check `SELECT count(*) FROM fr_rpt_farmer` |
| Totals lower than expected | Only `ACTIVE` records are counted by default | Pass `recordState` explicitly, or use `farmersByRecordState` |
| Figures lag the registry | Views not refreshed, or the BFF cache | Check the refresh job. Figures appear after the next refresh plus one cache period |
| `*_total` fields are `null` in `registryCoverage` | `GEO_LEVEL_TOTALS` not set for that level | Configure it |
| Too many database connections | Too many workers or replicas for the database's `max_connections` | Reduce workers or replicas, or raise `max_connections` |
