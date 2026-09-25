# AGENTS.md

Guidance for contributors and coding agents working in this repository. Read the
[README](README.md) and [docs/](docs/) first. This file lists the rules that are easy to get wrong.

## What this service is

A read-only FastAPI service that returns aggregate statistics about the farmer registry, one
endpoint per dashboard chart. Its only client is the OAN dashboards BFF, which caches the responses.

## Layout

```
app/main.py               app, lifespan (asyncpg pool), CORS, /health
app/core/config.py        settings (DATABASE_URL, ALLOWED_ORIGINS, GEO_LEVEL_TOTALS, …)
app/api/filters.py        ChartFilters + build_where_clause: the only place input becomes SQL
app/api/routes/charts.py  chart handlers
tests/                    pytest suite against a throw-away schema
docs/                     architecture, API reference, configuration, development, deployment, security
```

## Rules

### Data access
- Query **only** `fr_rpt_farmer` and `fr_rpt_land`. Never query the `g2p_register_*` tables.
- Group by a parcel attribute (tenure, land use) only on `fr_rpt_land`, joined to `fr_rpt_farmer`
  with `build_where_clause(filters, alias="f")`. Filters always select the **owning farmer**, so
  "in this zone" means the same thing on every chart, even where a parcel lies outside its owner's
  area.
- Aggregate area from `*_ha` columns only.
- `build_where_clause` counts `ACTIVE` records unless `recordState` is given. Pass
  `default_active=False` only for a breakdown by status.
- Return codes (`FEMALE`, `UNDER_25`, `OWNER`), not display labels, and do not re-bucket policy
  values such as age bands.

### SQL safety
- Interpolate only `where.sql` and literal column names. Every input value is bound through
  `where.values`.
- Pass fixed predicates as `build_where_clause(extra=…)`. Never write `{where.sql} AND …`: with no
  filters the clause is empty.
- Never take a column name, table name or sort order from input without an allow-list.

### Contract
- The response keys are a contract with the dashboards. Adding a key is fine. Renaming or removing
  one is a breaking change.
- Every chart's keys are listed in `CONTRACT` in `tests/test_charts.py`. Keep that list and
  `docs/api-reference.md` in step with the code.
- Cast aggregates in SQL (`::bigint`, `::float8`) so they serialise as numbers.

### Privacy
- Aggregates only: no names, IDs, contact details or coordinates in any response.

## Before handing off

```bash
make lint
make test
```

Both must pass. For a new or changed endpoint, also run it against a real registry database with no
filters and with every filter set.

## Conventions

- Python 3.11, async throughout, and one pool per worker. Do not open ad-hoc connections.
- Chart IDs and query parameters are camelCase (they are the dashboard's names). Python
  identifiers are snake_case.
- Conventional Commits (`feat(charts): …`, `fix: …`, `docs: …`).
- Never commit `.env`, virtual environments, or one-off patch scripts.
