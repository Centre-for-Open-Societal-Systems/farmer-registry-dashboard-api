"""Test fixtures.

Tests run against a real Postgres (the query SQL is the thing under test), but
never against the registry's data: each test gets a throw-away schema holding
small fr_rpt_* tables, and the pool's search_path points at it. The schema is
dropped afterwards.

TEST_DATABASE_URL picks the server; it defaults to the local
farmer-registry-v3 Postgres published on localhost:5432.
"""

import os
import uuid
from datetime import date

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/farmer_registry_db"),
)

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402

from app.api.dependencies import get_db_pool  # noqa: E402
from app.main import app  # noqa: E402

GEO = {
    "ET04a": ("region-ET04", "zone-ET0413", "woreda-ET041301", "kebele-ET041301301001"),
    "ET04b": ("region-ET04", "zone-ET0403", "woreda-ET040324", "kebele-ET040308888007"),
    "ET06": ("region-ET06", "zone-ET0603", "woreda-ET060309", "kebele-ET060103888064"),
}

SCHEMA_SQL = """
CREATE TABLE fr_rpt_farmer (
    farmer_id varchar PRIMARY KEY,
    record_status varchar,
    registration_date date,
    geo_1 text, geo_1_id text, geo_2_id text, geo_3_id text, geo_4_id text,
    gender varchar,
    age_band text,
    education_level varchar,
    main_farming_type varchar,
    total_land_ha numeric,
    owns_any_parcel boolean
);
CREATE TABLE fr_rpt_land (
    land_id varchar PRIMARY KEY,
    farmer_id varchar,
    record_status varchar,
    geo_1_id text, geo_2_id text, geo_3_id text, geo_4_id text,
    farming_type varchar,
    land_ownership_type varchar,
    is_owner_operated boolean,
    land_size_ha numeric(18, 6)
);
"""

# farmer_id, status, registered, geo, gender, age_band, education, farming type, land ha, owns
FARMERS = [
    ("f1", "ACTIVE", "2026-03-10", "ET04a", "FEMALE", "UNDER_25", "PRIMARY", "CROP", 2.0, True),
    ("f2", "ACTIVE", "2026-04-02", "ET04b", "MALE", "65_PLUS", "NONE", "LIVESTOCK", 3.0, False),
    ("f3", "INACTIVE", "2026-04-05", "ET06", "FEMALE", "35_49", "PRIMARY", "CROP", 1.0, True),
    ("f4", "ACTIVE", None, "ET06", "MALE", "25_34", None, "MIXED", None, False),
]

# land_id, farmer_id, status, geo, farming type, tenure, owner operated, ha
LANDS = [
    ("l1", "f1", "ACTIVE", "ET04a", "CROP", "OWNER", True, 1.5),
    ("l2", "f1", "ACTIVE", "ET04a", "CROP", "TENANT", False, 0.5),
    ("l3", "f2", "ACTIVE", "ET04b", "LIVESTOCK", "CROP_SHARE", False, 3.0),
    ("l4", "f3", "INACTIVE", "ET06", "CROP", "OWNER", True, 1.0),
]


async def _seed(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_SQL)
    for fid, status, reg, geo, gender, band, edu, ftype, ha, owns in FARMERS:
        g = GEO[geo]
        await conn.execute(
            "INSERT INTO fr_rpt_farmer VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
            fid,
            status,
            reg and date.fromisoformat(reg),
            g[0].split("-")[1],
            *g,
            gender,
            band,
            edu,
            ftype,
            ha,
            owns,
        )
    for lid, fid, status, geo, ftype, tenure, owner, ha in LANDS:
        await conn.execute(
            "INSERT INTO fr_rpt_land VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
            lid,
            fid,
            status,
            *GEO[geo],
            ftype,
            tenure,
            owner,
            ha,
        )


@pytest.fixture
async def pool():
    dsn = os.environ["DATABASE_URL"]
    schema = f"test_dash_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, server_settings={"search_path": schema})
        async with pool.acquire() as conn:
            await _seed(conn)
        yield pool
        await pool.close()
    finally:
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


@pytest.fixture
async def client(pool):
    app.dependency_overrides[get_db_pool] = lambda: pool
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
