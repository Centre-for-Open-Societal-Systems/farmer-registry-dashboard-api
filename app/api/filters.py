from dataclasses import dataclass, field
from typing import Literal

from fastapi import Query

View = Literal["farmer", "land"]

# Geography filters, outermost level first. The reporting views unpack the
# hierarchy by position, so geo_1 is whatever the deployment's top level is.
GEO_FILTERS = (
    ("region", "geo_1_id"),
    ("zone", "geo_2_id"),
    ("woreda", "geo_3_id"),
    ("kebele", "geo_4_id"),
)

# Attribute columns that differ between the per-farmer and per-parcel views.
FARMING_TYPE_COLUMN: dict[str, str] = {
    "farmer": "main_farming_type",
    "land": "farming_type",
}


def _given(value: str | None) -> bool:
    return bool(value) and value != "all"


class ChartFilters:
    """Query parameters shared by every chart endpoint."""

    def __init__(
        self,
        region: str | None = Query(None),
        zone: str | None = Query(None),
        woreda: str | None = Query(None),
        kebele: str | None = Query(None),
        farmingType: str | None = Query(None),
        recordState: str | None = Query(None),
    ):
        self.region = region
        self.zone = zone
        self.woreda = woreda
        self.kebele = kebele
        self.farmingType = farmingType
        self.recordState = recordState


@dataclass
class Where:
    """A WHERE clause and its bind values. `sql` is empty when nothing applies."""

    sql: str
    values: list = field(default_factory=list)


def build_where_clause(
    filters: ChartFilters,
    view: View = "farmer",
    extra: tuple[str, ...] = (),
    default_active: bool = True,
    alias: str = "",
) -> Where:
    """Build a parameterised WHERE clause for a reporting view.

    Only literal column names are interpolated; every filter value is bound as
    $n. `extra` holds fixed predicates (no user input) that must be ANDed in, so
    callers never concatenate onto the clause themselves: an empty clause plus
    "AND ..." is invalid SQL.

    Without an explicit recordState, only ACTIVE records are counted, matching
    what the registry considers a live farmer. Pass default_active=False for
    charts that break down by status.
    """
    prefix = f"{alias}." if alias else ""
    conditions: list[str] = []
    values: list = []

    def bind(value) -> str:
        values.append(value)
        return f"${len(values)}"

    for param, column in GEO_FILTERS:
        value = getattr(filters, param)
        if _given(value):
            col = f"{prefix}{column}"
            # Level value ids look like '<level>-<code>' (region-ET04). Accept
            # either the full id or the bare code without hard-coding level names.
            p = bind(value)
            conditions.append(f"({col} = {p} OR substr({col}, strpos({col}, '-') + 1) = {p})")

    if _given(filters.farmingType):
        col = f"{prefix}{FARMING_TYPE_COLUMN[view]}"
        conditions.append(f"LOWER({col}) = LOWER({bind(filters.farmingType)})")

    if _given(filters.recordState):
        conditions.append(f"LOWER({prefix}record_status) = LOWER({bind(filters.recordState)})")
    elif default_active:
        conditions.append(f"{prefix}record_status = 'ACTIVE'")

    conditions.extend(extra)

    if not conditions:
        return Where("")
    return Where("WHERE " + " AND ".join(conditions), values)
