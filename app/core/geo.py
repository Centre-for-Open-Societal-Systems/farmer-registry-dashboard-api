"""Which reporting-view position holds each dashboard geography level.

The reporting views unpack the hierarchy by position (geo_1 .. geo_5), in the
order of the country pack Master Data holds, and `fr_rpt_geo_levels` names each
position (depth, level_name). Packs differ: one starts at the region
(region/zone/woreda/kebele), another has a country root above it
(country/region/zone/woreda/village). The dashboards always ask for the four
levels below the country, so this module finds where they start.

Resolution, first match wins:
  1. GEO_TOP_LEVEL, if configured: the position of the dashboards' first level.
  2. fr_rpt_geo_levels: the first position whose level is not a country.
  3. Position 1 (the view cannot be read, e.g. before the reporting views exist).
Only a successful read of the view is cached; otherwise the next request tries
again, so a service started before the views were created corrects itself.
"""

import logging

import asyncpg

from app.core.config import settings

log = logging.getLogger(__name__)

# The dashboards' levels, outermost first. Their names are the API's filter
# parameters and response keys; the deployment's own level names may differ.
LEVELS: tuple[str, ...] = ("region", "zone", "woreda", "kebele")

# Level names treated as the hierarchy root rather than a dashboard level.
ROOT_LEVEL_NAMES = frozenset({"country", "nation"})

# The views unpack at most this many positions.
MAX_DEPTH = 5


def _check(top: int) -> int:
    if not 1 <= top <= MAX_DEPTH - len(LEVELS) + 1:
        raise ValueError(f"geography top level {top} leaves no room for {len(LEVELS)} levels in geo_1..geo_{MAX_DEPTH}")
    return top


def _configured() -> int | None:
    return _check(settings.GEO_TOP_LEVEL) if settings.GEO_TOP_LEVEL is not None else None


_top: int | None = _configured()


async def resolve(pool: asyncpg.Pool) -> None:
    """Find the top level once per process; a no-op after the first success."""
    global _top
    if _top is not None:
        return
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT depth, level_name FROM fr_rpt_geo_levels ORDER BY depth")
    except asyncpg.PostgresError as exc:
        log.warning("fr_rpt_geo_levels unreadable (%s); assuming geo_1 is the region level", exc)
        return
    top = next(
        (r["depth"] for r in rows if (r["level_name"] or "").strip().lower() not in ROOT_LEVEL_NAMES),
        1,
    )
    _top = _check(top)
    log.info(
        "geography levels: %s",
        ", ".join(f"{name}=geo_{position(name)}" for name in LEVELS),
    )


def position(level: str) -> int:
    """geo_N position of a dashboard level ('region', 'zone', 'woreda', 'kebele')."""
    return (_top or 1) + LEVELS.index(level)


def column(level: str, suffix: str = "_id") -> str:
    """Reporting-view column for a dashboard level, e.g. column('zone') -> 'geo_3_id'."""
    return f"geo_{position(level)}{suffix}"


def reset(top: int | None = None) -> None:
    """Forget the resolved level (tests), optionally forcing one."""
    global _top
    _top = _check(top) if top is not None else _configured()
