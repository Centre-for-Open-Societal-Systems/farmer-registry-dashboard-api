# AGENTS.md — farmer-registry-dashboard-api

Read-only FastAPI service that serves aggregate chart data for the GEN2 Farmer Registry dashboard
(Jira G2R-212). Its only consumer is the Elysia BFF in `oan_dashboards`. The BFF calls this service
through a 15-minute cache (`server/registry-cache.ts`), so each chart and filter combination is
requested at most once per TTL for each BFF process.

**The design doc is authoritative:** `oan_dashboards/docs/farmer-registry-dashboard-design.md`.
It covers the architecture, caching, the per-endpoint contract, and the numbered gap list (G-n).
Before changing behaviour, check whether the change closes or touches one of those gaps, and update
the table when it does.

## Layout

```
app/
  main.py                 FastAPI app: lifespan opens/closes the asyncpg pool, CORS, /health
  core/config.py          pydantic-settings (.env): DATABASE_URL, ALLOWED_ORIGINS, GEO_LEVEL_TOTALS
  api/dependencies.py     get_db_pool → request.app.state.pool (overridden in tests)
  api/filters.py          ChartFilters dependency + build_where_clause()
  api/routes/router.py    mounts charts at /charts
  api/routes/charts.py    one GET per chart
tests/                    pytest: contract, behaviour, filter and injection tests
```

## Run

```bash
cp .env.example .env          # set DATABASE_URL to farmer_registry_db
make dev                      # uvicorn --reload on :8005
docker compose up -d --build  # gunicorn 4×UvicornWorker, host :8005 → container :8000
curl localhost:8005/api/v1/charts/farmerKpis
open http://localhost:8005/docs   # OpenAPI
```

The database belongs to `farmer-registry-coss-v3`, and that stack also builds and runs this service
as `farmer-registry-dashboard-api` from `../farmer-registry-dashboard-api`. Start it with
`docker compose -p farmer-registry-v3 up -d`. Always pass `-p`: a bare `up` uses the compose
file's `name: farmer-registry` and attaches to retired volumes. To rebuild just this service in
that stack: `docker compose -p <project> build farmer-registry-dashboard-api && docker compose -p
<project> up -d --no-deps farmer-registry-dashboard-api`.

## Data source rules

- Query **only** the reporting views: `fr_rpt_farmer` (one row per farmer) and `fr_rpt_land`
  (one row per parcel). Never query `g2p_register_*` directly.
- **Use `fr_rpt_land` for anything grouped by a parcel attribute** (tenure, land use, parcel
  farming type). Pass `view="land"` to `build_where_clause` so the right columns are used.
- Aggregate area from `*_ha` columns only. The raw `land_size` column is free text.
- The views include every `record_status`. `build_where_clause` defaults to `ACTIVE`; pass
  `default_active=False` only for a breakdown by status.
- Age bands (`age_band`) and enums (`gender`, `land_ownership_type`, …) are returned as codes. The
  UI labels them, so do not re-bucket or translate them here.
- The view definitions live in `farmer-registry-coss-v3/docker/db-seed/reporting_views.sql` plus the
  generated `reporting.yaml`. Changing a column there is a change in the registry repo, and it needs
  a view refresh.

## Writing an endpoint

1. Take `filters: ChartFilters = Depends()` and call `build_where_clause(filters, view=…)`.
   Interpolate only `where.sql` and pass `*where.values` to the query (use the `fetch` helper).
2. **Every user value is bound as `$n`.** Never interpolate a query parameter, including sort order
   and column choice. Map those through a whitelist `dict`.
3. Fixed predicates go in `extra=(…)`. Joins use `alias=`. Never write `{where.sql} AND …`: when
   there are no filters the clause is empty, and the SQL breaks.
4. Return the **keys the UI reads**, and add them to `CONTRACT` in `tests/test_charts.py`.
5. Cast aggregates (`::bigint`, `::float8`). asyncpg returns `Decimal`, which serialises as a string.
6. Add the chart ID to `REGISTRY_CHARTS` in `oan_dashboards/server/registry-cache.ts`, or the BFF
   keeps serving it from local SQL.
7. Update the endpoint table in the design doc (§5.2).

## Security posture

- There is no auth. The service must only be reachable from the BFF (compose network or
  cluster-internal). Do not add a public ingress for it.
- CORS (`ALLOWED_ORIGINS`) is defence in depth. Browsers never call this API directly.
- Return aggregates only: no names, IDs, phone numbers or coordinates. For a new breakdown that can
  get down to a single kebele, consider a minimum cell size.

## Checks before you hand off

```bash
pip install -r requirements-dev.txt   # or: uv venv && uv pip install -r requirements-dev.txt
make lint                             # ruff check + format check
make test                             # needs Postgres; see below
```

The tests create a throw-away schema containing small `fr_rpt_*` tables, point the pool's
`search_path` at it, and drop it afterwards. Registry data is never read or changed.
`TEST_DATABASE_URL` selects the server (default `postgresql://postgres:postgres@localhost:5432/farmer_registry_db`).

Against a running stack, every chart must return 200 with no filters and with
`?region=ET04&recordState=ACTIVE`.

## Conventions

- Python 3.11, async throughout, and one pool per worker (created in `lifespan`). Do not open ad-hoc
  connections.
- Chart IDs and query-param names are camelCase (they are the UI's names). Python identifiers are
  snake_case.
- Remotes: `upstream` = `Centre-for-Open-Societal-Systems/farmer-registry-dashboard-api` (PR target:
  `develop`), and `fork` = `asmitonweb/coss-farmer-registry-dashboard-api` (push here). `origin` is
  the superseded personal repo; do not push new work there.
- Commits use Conventional Commits (`feat(charts): …`, `fix: …`). No AI co-author trailers.
- Do not commit scratch `patch_*` scripts, `.env`, or `.venv/`.
