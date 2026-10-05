import asyncpg
from fastapi import APIRouter, Depends

from app.api.dependencies import get_db_pool
from app.api.routes import charts
from app.core import geo
from app.core.auth import require_caller


async def resolve_geo_levels(pool: asyncpg.Pool = Depends(get_db_pool)) -> None:
    """Map the dashboard geography levels to reporting-view columns (once)."""
    await geo.resolve(pool)


# Authentication first: a rejected request never reaches the database.
api_router = APIRouter(dependencies=[Depends(require_caller), Depends(resolve_geo_levels)])
api_router.include_router(charts.router, prefix="/charts", tags=["charts"])
