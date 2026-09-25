import asyncpg
from fastapi import APIRouter, Depends

from app.api.dependencies import get_db_pool
from app.api.routes import charts
from app.core import geo


async def resolve_geo_levels(pool: asyncpg.Pool = Depends(get_db_pool)) -> None:
    """Map the dashboard geography levels to reporting-view columns (once)."""
    await geo.resolve(pool)


api_router = APIRouter(dependencies=[Depends(resolve_geo_levels)])
api_router.include_router(charts.router, prefix="/charts", tags=["charts"])
