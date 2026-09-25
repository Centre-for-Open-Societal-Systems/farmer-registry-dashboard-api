# Development

## Prerequisites

- Python 3.11 (or [uv](https://docs.astral.sh/uv/))
- A PostgreSQL server that is reachable locally:
  - for running the service: the farmer registry database, with its reporting views
  - for running the tests: any server where the test user can create a schema
- Docker, optionally, to run the service as a container

## Set up

```bash
cp .env.example .env                 # set DATABASE_URL
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

With uv instead:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv -r requirements-dev.txt
```

## Run

```bash
make dev                         # uvicorn with reload on http://localhost:8005
docker compose up -d --build     # production-like container on http://localhost:8005
```

The compose file requires `DATABASE_URL` and publishes the port on `127.0.0.1` only. When the
service runs in a container and the database runs on the host, use `host.docker.internal` as the
host in `DATABASE_URL`.

## Tests

```bash
make test        # pytest -q
```

The database tests need a PostgreSQL server, given as `TEST_DATABASE_URL` (a role that may create
schemas), but **not** registry data. Without `TEST_DATABASE_URL` they are skipped and only the unit
tests run:

```bash
TEST_DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db> make test
```

For each database test, a fixture in `tests/conftest.py`:

1. creates a uniquely named schema (`test_dash_<random>`)
2. creates small `fr_rpt_farmer` and `fr_rpt_land` tables in it and loads a fixed dataset of four
   farmers and four parcels
3. opens a pool whose `search_path` is that schema, and swaps it in for the app's pool through
   FastAPI dependency overrides
4. drops the schema afterwards

| File | Covers |
| --- | --- |
| `tests/test_charts.py` | The **contract** (exact response keys per chart), requests with no filters and with every filter set, and behaviour: the `ACTIVE` default, bare vs prefixed geo codes, per-parcel tenure, trend with owned area, age bands, coverage totals, SQL-injection handling, `/health` |
| `tests/test_filters.py` | `build_where_clause`: placeholder numbering, `all` handling, `extra`, `alias`, view-specific columns, and that values never appear in the SQL text |

## Lint and format

```bash
make lint        # ruff check + ruff format --check
make format      # apply fixes
```

The rules are in `pyproject.toml`: line length 120, rule sets E, F, I, B and UP. B008 is ignored,
because FastAPI's `Depends()` defaults trigger it.

## Adding a chart endpoint

1. **Pick the view.** Use `fr_rpt_farmer` for head counts and farmer attributes, and `fr_rpt_land`
   for anything grouped by a parcel attribute (see [Architecture](architecture.md#choosing-the-view)).
2. **Write the handler** in `app/api/routes/charts.py`:

   ```python
   @router.get("/farmersByMaritalStatus", response_model=Rows)
   async def get_farmers_by_marital_status(
       filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)
   ):
       where = build_where_clause(filters)
       query = f"""
           SELECT COALESCE(marital_status, 'Unknown') AS marital_status, COUNT(*)::bigint AS farmers
           FROM fr_rpt_farmer
           {where.sql}
           GROUP BY 1
           ORDER BY farmers DESC
       """
       return await fetch(pool, query, where)
   ```

   Rules:
   - interpolate only `where.sql`; every value comes from `where.values`
   - pass fixed predicates as `extra=(...)`, and never append `AND …` to `where.sql`, because with
     no filters it is empty
   - use `alias=` when the view is aliased in a join
   - cast every aggregate (`::bigint`, `::float8`)
   - return codes, not labels
3. **Add the response keys** to `CONTRACT` in `tests/test_charts.py`, and add behaviour tests for
   anything non-obvious.
4. **Document it** in [api-reference.md](api-reference.md).
5. **Register it in the dashboards.** Add the chart ID to the `farmer-registry` entry of
   `DASHBOARD_SERVICES` in the dashboards' `server/dashboard-services.ts`, so the BFF routes it
   here.

## Changing the reporting views

The views are owned by the farmer registry, not by this repository. A new column has to be added
there, and the view refreshed, before a query here can use it. Update the test fixture tables in
`tests/conftest.py` to match.
