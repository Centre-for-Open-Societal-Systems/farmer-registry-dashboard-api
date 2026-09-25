import pytest

from app.core.config import settings

# The keys each oan_dashboards component reads. A chart whose keys drift from
# these renders empty in the UI without any error, so pin them here.
CONTRACT = {
    "farmerKpis": {
        "total_farmers",
        "female_farmers",
        "male_farmers",
        "total_land_size",
        "avg_farm_size",
        "household_heads",
        "farmers_with_owned_land",
        "farmers_with_id",
        "farmers_without_id",
    },
    "farmersByRegion": {"region", "region_code", "farmers"},
    "farmersByZone": {"zone", "zone_code", "farmers"},
    "farmersByWoreda": {"woreda", "woreda_code", "farmers"},
    "farmersByKebele": {"kebele", "kebele_code", "farmers"},
    "farmersByFarmerId": {"id_status", "farmers"},
    "farmersByGender": {"gender", "farmers"},
    "farmersByType": {"farming_type", "farmers"},
    "farmersByAgeAndGender": {"age_group", "gender", "farmers"},
    "farmersByEducation": {"education", "farmers"},
    "landTenureSplit": {"ownership_type", "parcels", "area"},
    "registryTrendByMonth": {"period", "farmers", "total_area", "owned_area"},
    "registryCoverage": {
        f"{level}_{kind}" for level in ("regions", "zones", "woredas", "kebeles") for kind in ("covered", "total")
    },
    "farmersByRecordState": {"record_state", "farmers"},
}

STUBS = ["farmersByPsnpStatus", "farmersByImportStatus"]

ALL_FILTERS = {
    "region": "ET04",
    "zone": "ET0413",
    "woreda": "ET041301",
    "kebele": "ET041301301001",
    "farmingType": "crop",
    "recordState": "ACTIVE",
}


async def get(client, chart, **params):
    response = await client.get(f"/api/v1/charts/{chart}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("chart", sorted(CONTRACT))
async def test_contract_without_filters(client, chart):
    rows = await get(client, chart)
    assert rows, f"{chart} returned no rows"
    for row in rows:
        assert set(row) == CONTRACT[chart]


@pytest.mark.parametrize("chart", sorted(CONTRACT))
async def test_every_filter_at_once(client, chart):
    rows = await get(client, chart, **ALL_FILTERS)
    for row in rows:
        assert set(row) == CONTRACT[chart]


@pytest.mark.parametrize("chart", STUBS)
async def test_stubs_return_empty(client, chart):
    assert await get(client, chart) == []


async def test_kpis_count_active_by_default(client):
    [kpis] = await get(client, "farmerKpis")
    assert kpis["total_farmers"] == 3
    assert kpis["female_farmers"] == 1
    assert kpis["male_farmers"] == 2
    assert kpis["total_land_size"] == pytest.approx(5.0)
    assert (kpis["farmers_with_id"], kpis["farmers_without_id"]) == (2, 1)
    # Numbers, not Decimal-as-string.
    assert isinstance(kpis["avg_farm_size"], float)


async def test_record_state_filter_overrides_active_default(client):
    [kpis] = await get(client, "farmerKpis", recordState="inactive")
    assert kpis["total_farmers"] == 1


async def test_record_state_breakdown_sees_every_status(client):
    rows = await get(client, "farmersByRecordState")
    assert {r["record_state"]: r["farmers"] for r in rows} == {"ACTIVE": 3, "INACTIVE": 1}


@pytest.mark.parametrize("region", ["ET04", "region-ET04"])
async def test_geo_filter_accepts_bare_or_prefixed_code(client, region):
    [kpis] = await get(client, "farmerKpis", region=region)
    assert kpis["total_farmers"] == 2


async def test_region_code_is_bare(client):
    rows = await get(client, "farmersByRegion")
    assert {r["region_code"]: r["farmers"] for r in rows} == {"ET04": 2, "ET06": 1}


async def test_trend_without_filters(client):
    rows = await get(client, "registryTrendByMonth")
    # f4 has no registration date; f3 is INACTIVE.
    assert rows == [
        {"period": "2026-03", "farmers": 1, "total_area": 2.0, "owned_area": 1.5},
        {"period": "2026-04", "farmers": 1, "total_area": 3.0, "owned_area": 0.0},
    ]


async def test_tenure_is_per_parcel(client):
    rows = await get(client, "landTenureSplit")
    by_tenure = {r["ownership_type"]: (r["parcels"], r["area"]) for r in rows}
    # f1's 2 ha split across OWNER and TENANT rather than all going to one bucket;
    # l4 is INACTIVE.
    assert by_tenure == {"OWNER": (1, 1.5), "TENANT": (1, 0.5), "CROP_SHARE": (1, 3.0)}


@pytest.mark.parametrize(
    ("chart", "key", "expected"),
    [
        ("farmersByZone", "zone_code", {"ET0413": 1, "ET0403": 1, "ET0603": 1}),
        ("farmersByWoreda", "woreda_code", {"ET041301": 1, "ET040324": 1, "ET060309": 1}),
        ("farmersByKebele", "kebele_code", {"ET041301301001": 1, "ET040308888007": 1, "ET060103888064": 1}),
    ],
)
async def test_geo_breakdowns_use_bare_codes(client, chart, key, expected):
    rows = await get(client, chart)
    assert {r[key]: r["farmers"] for r in rows} == expected


async def test_geo_breakdown_respects_parent_filter(client):
    rows = await get(client, "farmersByWoreda", region="ET04")
    assert {r["woreda_code"] for r in rows} == {"ET041301", "ET040324"}


async def test_farmer_id_split(client):
    rows = await get(client, "farmersByFarmerId")
    # f4 has no functional record id; f3 is INACTIVE.
    assert {r["id_status"]: r["farmers"] for r in rows} == {"With Farmer ID": 2, "Without Farmer ID": 1}


async def test_tenure_follows_the_owning_farmers_geography(client):
    # l1 lies in ET06 but belongs to f1 in ET04, so it counts under ET04.
    rows = await get(client, "landTenureSplit", region="ET04")
    assert {r["ownership_type"]: r["parcels"] for r in rows} == {"OWNER": 1, "TENANT": 1, "CROP_SHARE": 1}
    # ET06's only farmer with land (f3) is INACTIVE, and l1 is not f3's.
    assert await get(client, "landTenureSplit", region="ET06") == []


async def test_age_bands_are_the_view_policy_bands(client):
    rows = await get(client, "farmersByAgeAndGender")
    assert [r["age_group"] for r in rows] == ["UNDER_25", "25_34", "65_PLUS"]


async def test_coverage_totals_come_from_settings(client, monkeypatch):
    [unset] = await get(client, "registryCoverage")
    assert unset["woredas_total"] is None
    assert unset["regions_covered"] == 2

    monkeypatch.setattr(settings, "GEO_LEVEL_TOTALS", {"woredas": 1138})
    [configured] = await get(client, "registryCoverage")
    assert configured["woredas_total"] == 1138
    assert configured["zones_total"] is None
    assert configured["woredas_covered"] == 3


async def test_injection_attempt_is_bound_as_a_value(client):
    [kpis] = await get(client, "farmerKpis", region="ET04' OR 1=1 --")
    assert kpis["total_farmers"] == 0


async def test_health(client):
    response = await client.get("/health")
    assert response.json() == {"status": "ok"}
