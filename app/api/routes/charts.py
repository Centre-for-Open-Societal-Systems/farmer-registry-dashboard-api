from fastapi import APIRouter, Depends, Query
import asyncpg
from typing import List, Dict, Any, Optional
from app.api.dependencies import get_db_pool

router = APIRouter()

def build_where_clause(region, zone, woreda, kebele, farmingType, recordState):
    conditions = []
    values = []
    idx = 1
    if region and region != 'all':
        conditions.append(f"geo_1_id = 'region-' || ${idx}")
        values.append(region)
        idx += 1
    if zone and zone != 'all':
        conditions.append(f"geo_2_id = 'zone-' || ${idx}")
        values.append(zone)
        idx += 1
    if woreda and woreda != 'all':
        conditions.append(f"geo_3_id = 'woreda-' || ${idx}")
        values.append(woreda)
        idx += 1
    if kebele and kebele != 'all':
        conditions.append(f"geo_4_id = 'kebele-' || ${idx}")
        values.append(kebele)
        idx += 1
    if farmingType and farmingType != 'all':
        conditions.append(f"LOWER(main_farming_type) = LOWER(${idx})")
        values.append(farmingType)
        idx += 1
    if recordState and recordState != 'all':
        conditions.append(f"LOWER(record_status) = LOWER(${idx})")
        values.append(recordState)
        idx += 1
    
    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)
    return where, values

@router.get("/farmerKpis", response_model=List[Dict[str, Any]])
async def get_farmer_kpis(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COUNT(DISTINCT farmer_id) AS total_farmers,
            SUM(CASE WHEN LOWER(gender) = 'female' THEN 1 ELSE 0 END) AS female_farmers,
            SUM(CASE WHEN LOWER(gender) = 'male' THEN 1 ELSE 0 END) AS male_farmers,
            COALESCE(SUM(total_land_ha), 0) AS total_land_size,
            COALESCE(AVG(total_land_ha), 0) AS avg_farm_size,
            0 AS household_heads,
            SUM(CASE WHEN owns_any_parcel THEN 1 ELSE 0 END) AS farmers_with_owned_land,
            0 AS farmers_with_id,
            0 AS farmers_without_id
        FROM fr_rpt_farmer
        {where}
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/farmersByRegion", response_model=List[Dict[str, Any]])
async def get_farmers_by_region(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COALESCE(geo_1, 'Unknown') as region,
            COALESCE(REPLACE(geo_1_id, 'region-', ''), 'Unknown') as region_code,
            COUNT(DISTINCT farmer_id) as farmers
        FROM fr_rpt_farmer
        {where}
        GROUP BY 1, 2
        ORDER BY farmers DESC
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/farmersByGender", response_model=List[Dict[str, Any]])
async def get_farmers_by_gender(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COALESCE(gender, 'Unknown') as gender,
            COUNT(DISTINCT farmer_id) as farmers
        FROM fr_rpt_farmer
        {where}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/farmersByType", response_model=List[Dict[str, Any]])
async def get_farmers_by_type(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COALESCE(main_farming_type, 'Unknown') as farming_type,
            COUNT(DISTINCT farmer_id) as farmers
        FROM fr_rpt_farmer
        {where}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/farmersByAgeAndGender", response_model=List[Dict[str, Any]])
async def get_farmers_by_age_and_gender(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COALESCE(age_band, 'Unknown') as age_group,
            COALESCE(gender, 'Unknown') as gender,
            COUNT(DISTINCT farmer_id) as farmers
        FROM fr_rpt_farmer
        {where}
        GROUP BY 1, 2
        ORDER BY age_group, gender
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/farmersByEducation", response_model=List[Dict[str, Any]])
async def get_farmers_by_education(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COALESCE(education_level, 'Unknown') as education,
            COUNT(DISTINCT farmer_id) as farmers
        FROM fr_rpt_farmer
        {where}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/landTenureSplit", response_model=List[Dict[str, Any]])
async def get_land_tenure_split(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COALESCE(main_tenure, 'Unknown') as ownership_type,
            SUM(parcel_count) as parcels,
            SUM(total_land_ha) as area
        FROM fr_rpt_farmer
        {where}
        GROUP BY 1
        ORDER BY parcels DESC
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/registryTrendByMonth", response_model=List[Dict[str, Any]])
async def get_registry_trend_by_month(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            DATE_TRUNC('month', registration_date) as period,
            COUNT(DISTINCT farmer_id) as farmers,
            SUM(total_land_ha) as total_area,
            AVG(total_land_ha) as avg_area
        FROM fr_rpt_farmer
        {where} AND registration_date IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/registryCoverage", response_model=List[Dict[str, Any]])
async def get_registry_coverage(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT COUNT(DISTINCT geo_3_id) as covered_woredas
        FROM fr_rpt_farmer
        {where}
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
        covered = records[0]['covered_woredas'] if records else 0
    return [{"woredas_total": 1138, "woredas_covered": covered}]

@router.get("/farmersByPsnpStatus", response_model=List[Dict[str, Any]])
async def get_farmers_by_psnp_status():
    return []

@router.get("/farmersByRecordState", response_model=List[Dict[str, Any]])
async def get_farmers_by_record_state(
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    woreda: Optional[str] = Query(None),
    kebele: Optional[str] = Query(None),
    farmingType: Optional[str] = Query(None),
    recordState: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    where, values = build_where_clause(region, zone, woreda, kebele, farmingType, recordState)
    query = f"""
        SELECT
            COALESCE(record_status, 'Unknown') as record_state,
            COUNT(DISTINCT farmer_id) as farmers
        FROM fr_rpt_farmer
        {where}
        GROUP BY 1
        ORDER BY farmers DESC
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *values)
    return [dict(r) for r in records]

@router.get("/farmersByImportStatus", response_model=List[Dict[str, Any]])
async def get_farmers_by_import_status():
    return []
