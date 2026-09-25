# Farmer Registry Dashboard API

The **dashboard service** of the OpenG2P farmer registry: a read-only HTTP service that serves
aggregate statistics about the registry to the OAN dashboards. It exposes one endpoint per dashboard
chart and computes each response from the registry's materialized reporting views (`fr_rpt_farmer`,
`fr_rpt_land`).

Each registry (farmer, livestock, crop, …) publishes its statistics through its own dashboard
service, and all of them share one HTTP contract. This service is the reference implementation of
that pattern. It is the only component that holds credentials for the farmer registry database:
the dashboards call the service and never the database.

- **Stack:** Python 3.11, FastAPI, asyncpg, gunicorn with Uvicorn workers
- **Consumer:** the OAN dashboards backend-for-frontend (BFF), which caches responses
- **Data:** aggregates only. The service never returns names, identifiers, contact details or
  coordinates

## Quick start

```bash
cp .env.example .env              # point DATABASE_URL at farmer_registry_db
docker compose up -d --build      # serves on http://localhost:8005
curl http://localhost:8005/health
curl "http://localhost:8005/api/v1/charts/farmerKpis?region=ET04"
```

Interactive OpenAPI docs are served at `http://localhost:8005/docs`.

A Postman collection with every endpoint is in `postman/`. Each request has contract tests, and the
filters are included but disabled. Import it, and set the `baseUrl` variable to the service's
address (default `http://localhost:8005`). To run it from the command line:

```bash
npx newman run "postman/Farmer Registry Dashboard Service.postman_collection.json" \
  --env-var baseUrl=http://localhost:8005
```

## Endpoints at a glance

| Endpoint | Returns |
| --- | --- |
| `GET /health` | Liveness and database connectivity |
| `GET /api/v1/charts/farmerKpis` | Headline totals: farmers, gender split, land area, owned land |
| `GET /api/v1/charts/farmersByRegion` | Farmers per top-level administrative unit |
| `GET /api/v1/charts/farmersByZone`, `farmersByWoreda`, `farmersByKebele` | Farmers per unit at levels 2–4, for map drill-down |
| `GET /api/v1/charts/farmersByFarmerId` | Farmers with and without a farmer ID |
| `GET /api/v1/charts/farmersByGender` | Farmers per gender |
| `GET /api/v1/charts/farmersByType` | Farmers per main farming type |
| `GET /api/v1/charts/farmersByAgeAndGender` | Farmers per age band and gender |
| `GET /api/v1/charts/farmersByEducation` | Farmers per education level |
| `GET /api/v1/charts/farmersByRecordState` | Farmers per record status |
| `GET /api/v1/charts/landTenureSplit` | Parcels and hectares per tenure type |
| `GET /api/v1/charts/registryTrendByMonth` | Registrations and land area per month |
| `GET /api/v1/charts/registryCoverage` | Administrative units covered, per level |

All chart endpoints accept the same filters: `region`, `zone`, `woreda`, `kebele`, `farmingType`
and `recordState`. See the [API reference](docs/api-reference.md) for the full contract.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Where the service sits, data flow, data sources, design decisions |
| [API reference](docs/api-reference.md) | Every endpoint, parameter and response field, with examples |
| [Configuration](docs/configuration.md) | Environment variables |
| [Development](docs/development.md) | Local setup, tests, linting, adding an endpoint |
| [Deployment and operations](docs/deployment.md) | Container image, sizing, health checks, monitoring, troubleshooting |
| [Security](docs/security.md) | Threat model, SQL-injection controls, network exposure, data protection |
| [AGENTS.md](AGENTS.md) | Rules for contributors and coding agents working in this repository |

## License

MIT. See [LICENSE](LICENSE).
