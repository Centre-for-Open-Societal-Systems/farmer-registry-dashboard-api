from app.api.filters import ChartFilters, build_where_clause


def filters(**kwargs) -> ChartFilters:
    params = dict.fromkeys(("region", "zone", "woreda", "kebele", "farmingType", "recordState"))
    params.update(kwargs)
    return ChartFilters(**params)


def test_no_filters_defaults_to_active():
    where = build_where_clause(filters())
    assert where.sql == "WHERE record_status = 'ACTIVE'"
    assert where.values == []


def test_no_filters_and_no_default_is_empty():
    where = build_where_clause(filters(), default_active=False)
    assert where.sql == ""


def test_all_is_ignored():
    where = build_where_clause(filters(region="all", farmingType="all"), default_active=False)
    assert where.sql == ""


def test_placeholders_are_numbered_in_bind_order():
    where = build_where_clause(filters(region="ET04", woreda="ET041301", farmingType="crop", recordState="active"))
    assert where.values == ["ET04", "ET041301", "crop", "active"]
    for n in range(1, 5):
        assert f"${n}" in where.sql
    assert "$5" not in where.sql
    assert "'ACTIVE'" not in where.sql


def test_extra_predicates_are_anded_even_without_filters():
    where = build_where_clause(filters(), default_active=False, extra=("x IS NOT NULL",))
    assert where.sql == "WHERE x IS NOT NULL"


def test_view_selects_farming_type_column():
    assert "main_farming_type" in build_where_clause(filters(farmingType="crop")).sql
    land = build_where_clause(filters(farmingType="crop"), view="land").sql
    assert "LOWER(farming_type)" in land


def test_alias_prefixes_every_column():
    where = build_where_clause(filters(region="ET04"), alias="f", extra=("f.registration_date IS NOT NULL",))
    assert "f.geo_1_id" in where.sql
    assert "f.record_status = 'ACTIVE'" in where.sql


def test_values_never_reach_the_sql_text():
    evil = "ET04' OR 1=1 --"
    where = build_where_clause(filters(region=evil, farmingType=evil, recordState=evil))
    assert evil not in where.sql
