"""Chart endpoints for the GEN2 farmer registry dashboard.

Each endpoint returns a JSON array of row objects whose keys match what the
oan_dashboards components read (the legacy chart SQL shapes). Read only from
the fr_rpt_* reporting views; see AGENTS.md for the rules.
"""

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends

from app.api.dependencies import get_db_pool
from app.api.filters import ChartFilters, Where, build_where_clause
from app.core.config import settings

router = APIRouter()

Rows = list[dict[str, Any]]


async def fetch(pool: asyncpg.Pool, query: str, where: Where) -> Rows:
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *where.values)
    return [dict(r) for r in records]


@router.get("/farmerKpis", response_model=Rows)
async def get_farmer_kpis(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters)
    query = f"""
        SELECT
            COUNT(*)::bigint                                         AS total_farmers,
            COUNT(*) FILTER (WHERE UPPER(gender) = 'FEMALE')::bigint AS female_farmers,
            COUNT(*) FILTER (WHERE UPPER(gender) = 'MALE')::bigint   AS male_farmers,
            COALESCE(SUM(total_land_ha), 0)::float8                  AS total_land_size,
            COALESCE(AVG(total_land_ha), 0)::float8                  AS avg_farm_size,
            0                                                        AS household_heads,
            COUNT(*) FILTER (WHERE owns_any_parcel)::bigint          AS farmers_with_owned_land,
            0                                                        AS farmers_with_id,
            0                                                        AS farmers_without_id
        FROM fr_rpt_farmer
        {where.sql}
    """
    return await fetch(pool, query, where)


@router.get("/farmersByRegion", response_model=Rows)
async def get_farmers_by_region(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters)
    query = f"""
        SELECT
            COALESCE(geo_1, 'Unknown')                                          AS region,
            COALESCE(substr(geo_1_id, strpos(geo_1_id, '-') + 1), 'Unknown')   AS region_code,
            COUNT(*)::bigint                                                    AS farmers
        FROM fr_rpt_farmer
        {where.sql}
        GROUP BY 1, 2
        ORDER BY farmers DESC
    """
    return await fetch(pool, query, where)


@router.get("/farmersByGender", response_model=Rows)
async def get_farmers_by_gender(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters)
    query = f"""
        SELECT COALESCE(gender, 'Unknown') AS gender, COUNT(*)::bigint AS farmers
        FROM fr_rpt_farmer
        {where.sql}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    return await fetch(pool, query, where)


@router.get("/farmersByType", response_model=Rows)
async def get_farmers_by_type(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters)
    query = f"""
        SELECT COALESCE(main_farming_type, 'Unknown') AS farming_type, COUNT(*)::bigint AS farmers
        FROM fr_rpt_farmer
        {where.sql}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    return await fetch(pool, query, where)


@router.get("/farmersByAgeAndGender", response_model=Rows)
async def get_farmers_by_age_and_gender(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    # age_band is policy defined in the registry's reporting.yaml
    # (UNDER_25, 25_34, 35_49, 50_64, 65_PLUS, UNKNOWN); the UI labels it.
    where = build_where_clause(filters)
    query = f"""
        SELECT
            COALESCE(age_band, 'UNKNOWN')  AS age_group,
            COALESCE(gender, 'Unknown')    AS gender,
            COUNT(*)::bigint               AS farmers
        FROM fr_rpt_farmer
        {where.sql}
        GROUP BY 1, 2
        ORDER BY
            CASE COALESCE(age_band, 'UNKNOWN')
                WHEN 'UNDER_25' THEN 1 WHEN '25_34' THEN 2 WHEN '35_49' THEN 3
                WHEN '50_64' THEN 4 WHEN '65_PLUS' THEN 5 ELSE 6
            END,
            gender
    """
    return await fetch(pool, query, where)


@router.get("/farmersByEducation", response_model=Rows)
async def get_farmers_by_education(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters)
    query = f"""
        SELECT COALESCE(education_level, 'Unknown') AS education, COUNT(*)::bigint AS farmers
        FROM fr_rpt_farmer
        {where.sql}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    return await fetch(pool, query, where)


@router.get("/landTenureSplit", response_model=Rows)
async def get_land_tenure_split(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    # Tenure is a parcel attribute, so this must be per parcel (fr_rpt_land):
    # rolling area up to the farmer first would put all of a farmer's hectares
    # under their largest parcel's tenure.
    where = build_where_clause(filters, view="land")
    query = f"""
        SELECT
            COALESCE(land_ownership_type, 'UNKNOWN')   AS ownership_type,
            COUNT(*)::bigint                            AS parcels,
            COALESCE(SUM(land_size_ha), 0)::float8      AS area
        FROM fr_rpt_land
        {where.sql}
        GROUP BY 1
        ORDER BY parcels DESC
    """
    return await fetch(pool, query, where)


@router.get("/registryTrendByMonth", response_model=Rows)
async def get_registry_trend_by_month(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters, alias="f", extra=("f.registration_date IS NOT NULL",))
    query = f"""
        WITH owned AS (
            SELECT farmer_id, SUM(land_size_ha) AS owned_ha
            FROM fr_rpt_land
            WHERE is_owner_operated AND record_status = 'ACTIVE'
            GROUP BY farmer_id
        )
        SELECT
            TO_CHAR(DATE_TRUNC('month', f.registration_date), 'YYYY-MM') AS period,
            COUNT(*)::bigint                                              AS farmers,
            COALESCE(SUM(f.total_land_ha), 0)::float8                     AS total_area,
            COALESCE(SUM(o.owned_ha), 0)::float8                          AS owned_area
        FROM fr_rpt_farmer f
        LEFT JOIN owned o ON o.farmer_id = f.farmer_id
        {where.sql}
        GROUP BY 1
        ORDER BY 1
    """
    return await fetch(pool, query, where)


@router.get("/registryCoverage", response_model=Rows)
async def get_registry_coverage(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters)
    query = f"""
        SELECT
            COUNT(DISTINCT geo_1_id)::bigint AS regions_covered,
            COUNT(DISTINCT geo_2_id)::bigint AS zones_covered,
            COUNT(DISTINCT geo_3_id)::bigint AS woredas_covered,
            COUNT(DISTINCT geo_4_id)::bigint AS kebeles_covered
        FROM fr_rpt_farmer
        {where.sql}
    """
    rows = await fetch(pool, query, where)
    covered = rows[0] if rows else {}
    totals = settings.GEO_LEVEL_TOTALS
    result: dict[str, Any] = {}
    for level in ("regions", "zones", "woredas", "kebeles"):
        result[f"{level}_covered"] = covered.get(f"{level}_covered", 0)
        result[f"{level}_total"] = totals.get(level)
    return [result]


@router.get("/farmersByRecordState", response_model=Rows)
async def get_farmers_by_record_state(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    # A breakdown by status must see every status, so no ACTIVE default here.
    where = build_where_clause(filters, default_active=False)
    query = f"""
        SELECT COALESCE(record_status, 'Unknown') AS record_state, COUNT(*)::bigint AS farmers
        FROM fr_rpt_farmer
        {where.sql}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    return await fetch(pool, query, where)


# GEN2 has no PSNP or legacy-import concept yet; the UI treats [] as "no data".
@router.get("/farmersByPsnpStatus", response_model=Rows)
async def get_farmers_by_psnp_status():
    return []


@router.get("/farmersByImportStatus", response_model=Rows)
async def get_farmers_by_import_status():
    return []
