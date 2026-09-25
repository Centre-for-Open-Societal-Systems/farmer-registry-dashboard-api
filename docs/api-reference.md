# API reference

- **Base URL:** `http://<host>:8005` when run with the provided compose file (the container listens
  on `8000`).
- **Route prefix:** `/api/v1` (configurable with `API_V1_STR`).
- **Methods and responses:** every endpoint is `GET` and returns `application/json`.
- **OpenAPI:** the generated schema is at `/openapi.json`, with an interactive UI at `/docs`.

## Conventions

### Response shape

Every chart endpoint returns a **JSON array of row objects**. There is no envelope:

- a chart with no matching data returns `[]`
- a single-figure chart (`farmerKpis`, `registryCoverage`) returns an array with one object

Numbers are JSON numbers:

- counts are integers
- areas and averages are floating-point hectares

Categorical values are returned as the registry's **codes**, not display labels (for example
`FEMALE`, `UNDER_25`, `CROP_SHARE`), and the client is responsible for labelling them. A missing
category is returned as `"Unknown"`, or as `"UNKNOWN"` for age bands and tenure.

### Response keys are a contract

The key names of each chart are relied on by the dashboards, and the test suite pins them. Renaming
or removing a key is a breaking change. Adding a key is not.

## Common filter parameters

Every chart endpoint accepts these optional query parameters. The value `all` behaves the same as
leaving the parameter out.

| Parameter | Type | Matches | Notes |
| --- | --- | --- | --- |
| `region` | string | first dashboard geography level | Either the bare code (`ET04`) or the full level value id (`region-ET04`) |
| `zone` | string | second level | as above |
| `woreda` | string | third level | as above |
| `kebele` | string | fourth level | as above |
| `farmingType` | string | the farmer's main farming type | Case-insensitive, for example `crop`, `LIVESTOCK`, `mixed` |
| `recordState` | string | `record_status` | Case-insensitive. **If omitted, only `ACTIVE` records are counted**, except in `farmersByRecordState` |

The filters combine with AND. Geographic filters do not have to be consistent with each other, but a
zone outside the selected region simply matches nothing. Unknown parameters are ignored.

The level names used above (region, zone, woreda, kebele) are the parameter names the API accepts.
The API matches on the position in the hierarchy, so a deployment whose levels have other names uses
the same parameters.

**Where the four levels start.** The reporting views store the hierarchy by position (`geo_1` …
`geo_5`), in the order of the country pack, and `fr_rpt_geo_levels` names each position. Some packs
start at the region (`region, zone, woreda, kebele`). Others have a country root above it
(`country, region, zone, woreda, village`). The API reads `fr_rpt_geo_levels` and maps `region` to
the first position that is not a country (`country` or `nation`), with the other three levels
below it. With a country root, `region` is `geo_2` and `kebele` is `geo_5`, so responses carry
region codes (`ET04`), never the country (`ET`). `GEO_TOP_LEVEL` overrides the detection (see
[Configuration](configuration.md)).

## Endpoints

### `GET /health`

Checks that the process is serving and that the database answers `SELECT 1`.

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | `{"status": "ok"}` | Healthy |
| 500 | error | The database is unreachable or the pool is exhausted |

---

### `GET /api/v1/charts/farmerKpis`

Headline figures over the filtered farmers. Returns one object.

| Field | Type | Meaning |
| --- | --- | --- |
| `total_farmers` | integer | Farmers matching the filters |
| `female_farmers` | integer | … with gender `FEMALE` |
| `male_farmers` | integer | … with gender `MALE` |
| `total_land_size` | number | Sum of `total_land_ha`, in hectares |
| `avg_farm_size` | number | Average `total_land_ha` per farmer, in hectares |
| `farmers_with_owned_land` | integer | Farmers with at least one owner-operated parcel |
| `household_heads` | integer | Always `0` (not available in the reporting views) |
| `farmers_with_id` | integer | Farmers with a farmer ID (registry functional record id) |
| `farmers_without_id` | integer | Farmers without one |

```json
[{"total_farmers": 195, "female_farmers": 93, "male_farmers": 100,
  "total_land_size": 542.41933, "avg_farm_size": 4.2376, "farmers_with_owned_land": 61,
  "household_heads": 0, "farmers_with_id": 195, "farmers_without_id": 0}]
```

---

### `GET /api/v1/charts/farmersByRegion`

Farmers per top-level administrative unit, largest first.

| Field | Type | Meaning |
| --- | --- | --- |
| `region` | string | Unit name |
| `region_code` | string | Unit code without the level prefix (for example `ET04`). Use it to join to map features |
| `farmers` | integer | Farmers in the unit |

```json
[{"region": "Oromia", "region_code": "ET04", "farmers": 195}]
```

---

### `GET /api/v1/charts/farmersByZone`, `farmersByWoreda`, `farmersByKebele`

Farmers per unit at the second, third and fourth dashboard levels (zone, woreda, kebele), largest first. Combine with the parent filters to
drill down, for example `farmersByWoreda?region=ET04&zone=ET0410` for the woredas of one zone.

| Chart | Fields |
| --- | --- |
| `farmersByZone` | `zone` (name), `zone_code`, `farmers` |
| `farmersByWoreda` | `woreda`, `woreda_code`, `farmers` |
| `farmersByKebele` | `kebele`, `kebele_code`, `farmers` |

Codes are returned without the level prefix (for example `ET0410`, `ET041016`) and match standard
administrative P-codes, so they join directly to map boundaries. A few units whose hierarchy skips a
level in the registry (for example special woredas directly under a region) appear at the level
their position implies.

```json
[{"woreda": "Girawa", "woreda_code": "ET041016", "farmers": 3},
 {"woreda": "Meta", "woreda_code": "ET041009", "farmers": 2}]
```

---

### `GET /api/v1/charts/farmersByFarmerId`

Farmers with and without a farmer ID (the registry's functional record id).

| Field | Type | Meaning |
| --- | --- | --- |
| `id_status` | string | `With Farmer ID` or `Without Farmer ID` |
| `farmers` | integer | Farmers |

---

### `GET /api/v1/charts/farmersByGender`

| Field | Type | Meaning |
| --- | --- | --- |
| `gender` | string | Gender code (`MALE`, `FEMALE`, …) or `Unknown` |
| `farmers` | integer | Farmers |

```json
[{"gender": "MALE", "farmers": 100}, {"gender": "FEMALE", "farmers": 93}, {"gender": "Unknown", "farmers": 2}]
```

---

### `GET /api/v1/charts/farmersByType`

| Field | Type | Meaning |
| --- | --- | --- |
| `farming_type` | string | The farmer's main farming type, which is the type of their largest parcel (`CROP`, `LIVESTOCK`, `MIXED`, …), or `Unknown` |
| `farmers` | integer | Farmers |

---

### `GET /api/v1/charts/farmersByAgeAndGender`

One row per age band and gender, ordered youngest to oldest.

| Field | Type | Meaning |
| --- | --- | --- |
| `age_group` | string | `UNDER_25`, `25_34`, `35_49`, `50_64`, `65_PLUS` or `UNKNOWN` |
| `gender` | string | Gender code or `Unknown` |
| `farmers` | integer | Farmers |

The bands are defined by the registry's reporting configuration, not by this service.

---

### `GET /api/v1/charts/farmersByEducation`

| Field | Type | Meaning |
| --- | --- | --- |
| `education` | string | Education level code (for example `BASIC`, `HIGHER_EDUCATION`) or `Unknown` |
| `farmers` | integer | Farmers |

---

### `GET /api/v1/charts/farmersByRecordState`

Farmers per record status. Unlike every other chart, this one **does not** default to `ACTIVE`: it
covers every status unless `recordState` is given.

| Field | Type | Meaning |
| --- | --- | --- |
| `record_state` | string | Registry record status (for example `ACTIVE`) or `Unknown` |
| `farmers` | integer | Farmers |

---

### `GET /api/v1/charts/landTenureSplit`

Parcels and area per tenure type, computed **per parcel** from `fr_rpt_land`, for the land held by
the farmers that match the filters. All filters apply to the **owning farmer** (geography, farming
type, record status), as in every other chart. A parcel located outside its owner's area is still
counted under the owner's area. Only active parcels are counted.

| Field | Type | Meaning |
| --- | --- | --- |
| `ownership_type` | string | `OWNER`, `TENANT`, `CROP_SHARE`, … or `UNKNOWN` |
| `parcels` | integer | Number of parcels |
| `area` | number | Sum of `land_size_ha`, in hectares |

```json
[{"ownership_type": "CROP_SHARE", "parcels": 180, "area": 616.49},
 {"ownership_type": "OWNER", "parcels": 170, "area": 466.21},
 {"ownership_type": "TENANT", "parcels": 159, "area": 436.30}]
```

---

### `GET /api/v1/charts/registryTrendByMonth`

Registrations per calendar month, oldest first. Farmers without a registration date are excluded.

| Field | Type | Meaning |
| --- | --- | --- |
| `period` | string | Month, `YYYY-MM` |
| `farmers` | integer | Farmers registered in that month |
| `total_area` | number | Their total land, in hectares |
| `owned_area` | number | Their owner-operated land (active parcels), in hectares |

```json
[{"period": "2026-03", "farmers": 120, "total_area": 410.5, "owned_area": 150.25},
 {"period": "2026-04", "farmers": 380, "total_area": 1108.5, "owned_area": 315.96}]
```

---

### `GET /api/v1/charts/registryCoverage`

The number of distinct administrative units that contain matching farmers, per level, next to the
national number of units. Returns one object.

| Field | Type | Meaning |
| --- | --- | --- |
| `regions_covered`, `zones_covered`, `woredas_covered`, `kebeles_covered` | integer | Distinct units at levels 1 to 4 with at least one matching farmer |
| `regions_total`, `zones_total`, `woredas_total`, `kebeles_total` | integer or `null` | National unit count from `GEO_LEVEL_TOTALS`. `null` when not configured for that level |

```json
[{"regions_covered": 15, "regions_total": null, "zones_covered": 85, "zones_total": null,
  "woredas_covered": 355, "woredas_total": 1138, "kebeles_covered": 496, "kebeles_total": null}]
```

---

### `GET /api/v1/charts/farmersByPsnpStatus`, `GET /api/v1/charts/farmersByImportStatus`

These always return `[]`. They are placeholders for concepts the registry does not model yet, and
they keep the dashboard's batched requests stable.

## Errors

| Status | When | Body |
| --- | --- | --- |
| 404 | Unknown path | `{"detail": "Not Found"}` |
| 500 | Database error or unreachable database | `Internal Server Error` |

A filter value that matches nothing is not an error. The chart returns zero counts or `[]`.

## Versioning

The API is versioned in its path (`/api/v1`). Within v1:

- adding endpoints, response fields or optional parameters is allowed
- removing or renaming response keys, changing a field's type, or changing a default (such as the
  `ACTIVE` record filter) needs a new version, or a coordinated change with the dashboards
