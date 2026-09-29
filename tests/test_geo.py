import pytest

from app.api.filters import ChartFilters, build_where_clause
from app.core import geo
from app.core.config import settings


@pytest.fixture(autouse=True)
def fresh_levels():
    geo.reset()
    yield
    geo.reset()


def test_default_is_region_first():
    assert [geo.column(level) for level in geo.LEVELS] == ["geo_1_id", "geo_2_id", "geo_3_id", "geo_4_id"]
    assert geo.column("region", "") == "geo_1"


def test_country_root_shifts_every_level():
    geo.reset(2)
    assert [geo.column(level) for level in geo.LEVELS] == ["geo_2_id", "geo_3_id", "geo_4_id", "geo_5_id"]


def test_filters_follow_the_levels():
    geo.reset(2)
    params = dict.fromkeys(("region", "zone", "woreda", "kebele", "farmingType", "recordState"))
    where = build_where_clause(ChartFilters(**{**params, "zone": "ET0413"}))
    assert "geo_3_id" in where.sql
    assert "geo_2_id" not in where.sql


@pytest.mark.parametrize("top", [0, 3])
def test_top_level_must_leave_room_for_every_level(top):
    with pytest.raises(ValueError):
        geo.reset(top)


def test_configured_top_level_wins(monkeypatch):
    monkeypatch.setattr(settings, "GEO_TOP_LEVEL", 2)
    geo.reset()
    assert geo.position("region") == 2


async def test_resolved_from_the_levels_view(pool):
    await geo.resolve(pool)
    async with pool.acquire() as conn:
        first = await conn.fetchval("SELECT level_name FROM fr_rpt_geo_levels ORDER BY depth LIMIT 1")
    assert geo.position("region") == (2 if first == "country" else 1)


async def test_unreadable_view_falls_back_and_retries(pool):
    async with pool.acquire() as conn:
        await conn.execute("ALTER TABLE fr_rpt_geo_levels RENAME TO geo_levels_hidden")
    await geo.resolve(pool)
    assert geo.position("region") == 1
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE geo_levels_hidden")
        await conn.execute("CREATE TABLE fr_rpt_geo_levels (depth integer, level_name text)")
        await conn.execute("INSERT INTO fr_rpt_geo_levels VALUES (1, 'Country'), (2, 'region')")
    await geo.resolve(pool)
    assert geo.position("region") == 2


async def _set_levels(pool, *names):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM fr_rpt_geo_levels")
        await conn.executemany("INSERT INTO fr_rpt_geo_levels VALUES ($1, $2)", list(enumerate(names, start=1)))


async def test_rebuilt_hierarchy_is_followed_after_the_recheck_interval(pool, monkeypatch):
    # The registry rebuilt its views without the country root while the
    # service was running: the old mapping must not outlive the interval.
    monkeypatch.setattr(settings, "GEO_LEVELS_RECHECK_SECONDS", 0)
    await _set_levels(pool, "country", "region", "zone", "woreda", "village")
    await geo.resolve(pool)
    assert geo.position("region") == 2
    await _set_levels(pool, "region", "zone", "woreda", "kebele")
    await geo.resolve(pool)
    assert geo.position("region") == 1


async def test_levels_are_not_reread_within_the_interval(pool, monkeypatch):
    monkeypatch.setattr(settings, "GEO_LEVELS_RECHECK_SECONDS", 3600)
    await _set_levels(pool, "country", "region", "zone", "woreda", "village")
    await geo.resolve(pool)
    await _set_levels(pool, "region", "zone", "woreda", "kebele")
    await geo.resolve(pool)
    assert geo.position("region") == 2
