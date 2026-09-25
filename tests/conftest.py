"""Test fixtures.

Tests run against a real Postgres (the query SQL is the thing under test), but
never against the registry's data: each test gets a throw-away schema holding
small fr_rpt_* tables, and the pool's search_path points at it. The schema is
dropped afterwards.

TEST_DATABASE_URL names the server, with a role that may create schemas. It is
never defaulted: without it, the database tests are skipped and only the pure
unit tests run.

Every database test runs against two hierarchy layouts (see app/core/geo.py):
"region" (geo_1 is the region, as in a region-rooted pack) and "country" (a
country root at geo_1, everything else one position down, as in a pack whose
hierarchy starts at the country). The same assertions must hold for both.
"""

import os
import uuid
from datetime import date

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# The app's settings require DATABASE_URL at import time; the tests replace
# the pool, so the value is never used to connect.
os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost/unused")

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402

from app.api.dependencies import get_db_pool  # noqa: E402
from app.core import geo as geo_levels  # noqa: E402
from app.main import app  # noqa: E402

GEO = {
    "ET04a": ("region-ET04", "zone-ET0413", "woreda-ET041301", "kebele-ET041301301001"),
    "ET04b": ("region-ET04", "zone-ET0403", "woreda-ET040324", "kebele-ET040308888007"),
    "ET06": ("region-ET06", "zone-ET0603", "woreda-ET060309", "kebele-ET060103888064"),
}

# Level names per layout, as fr_rpt_geo_levels publishes them.
LAYOUTS = {
    "region": ("region", "zone", "woreda", "kebele"),
    "country": ("country", "region", "zone", "woreda", "village"),
}
COUNTRY_ROOT = ("Ethiopia", "ET")

SCHEMA_SQL = """
CREATE TABLE fr_rpt_geo_levels (depth integer, level_name text);
CREATE TABLE fr_rpt_farmer (
    farmer_id varchar PRIMARY KEY,
    functional_record_id varchar,
    record_status varchar,
    registration_date date,
    geo_1 text, geo_2 text, geo_3 text, geo_4 text, geo_5 text,
    geo_1_id text, geo_2_id text, geo_3_id text, geo_4_id text, geo_5_id text,
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
    geo_1_id text, geo_2_id text, geo_3_id text, geo_4_id text, geo_5_id text,
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
# l1 lies outside its owner's region on purpose: charts filter land by the
# owning farmer's geography, not the parcel's.
LANDS = [
    ("l1", "f1", "ACTIVE", "ET06", "CROP", "OWNER", True, 1.5),
    ("l2", "f1", "ACTIVE", "ET04a", "CROP", "TENANT", False, 0.5),
    ("l3", "f2", "ACTIVE", "ET04b", "LIVESTOCK", "CROP_SHARE", False, 3.0),
    ("l4", "f3", "INACTIVE", "ET06", "CROP", "OWNER", True, 1.0),
]


def _positions(layout: str, units: tuple[str, ...]) -> tuple[list, list]:
    """geo_1..geo_5 names and ids for a unit path in the given layout."""
    names = [f"{unit} name" for unit in units]
    ids = list(units)
    if layout == "country":
        names, ids = [COUNTRY_ROOT[0], *names], [COUNTRY_ROOT[1], *ids]
    pad = [None] * (5 - len(ids))
    return names + pad, ids + pad


async def _seed(conn: asyncpg.Connection, layout: str) -> None:
    await conn.execute(SCHEMA_SQL)
    await conn.executemany("INSERT INTO fr_rpt_geo_levels VALUES ($1, $2)", list(enumerate(LAYOUTS[layout], start=1)))
    for fid, status, reg, geo, gender, band, edu, ftype, ha, owns in FARMERS:
        names, ids = _positions(layout, GEO[geo])
        await conn.execute(
            """INSERT INTO fr_rpt_farmer (
                   farmer_id, functional_record_id, record_status, registration_date,
                   geo_1, geo_2, geo_3, geo_4, geo_5, geo_1_id, geo_2_id, geo_3_id, geo_4_id, geo_5_id,
                   gender, age_band, education_level, main_farming_type, total_land_ha, owns_any_parcel)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)""",
            fid,
            None if fid == "f4" else f"FR-{fid}",
            status,
            reg and date.fromisoformat(reg),
            *names,
            *ids,
            gender,
            band,
            edu,
            ftype,
            ha,
            owns,
        )
    for lid, fid, status, geo, ftype, tenure, owner, ha in LANDS:
        await conn.execute(
            "INSERT INTO fr_rpt_land VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
            lid,
            fid,
            status,
            *_positions(layout, GEO[geo])[1],
            ftype,
            tenure,
            owner,
            ha,
        )


@pytest.fixture(params=sorted(LAYOUTS))
async def pool(request):
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    dsn = TEST_DATABASE_URL
    schema = f"test_dash_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, server_settings={"search_path": schema})
        async with pool.acquire() as conn:
            await _seed(conn, request.param)
        yield pool
        await pool.close()
    finally:
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


@pytest.fixture
async def client(pool):
    app.dependency_overrides[get_db_pool] = lambda: pool
    geo_levels.reset()  # resolved afresh from this schema's fr_rpt_geo_levels
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    geo_levels.reset()
