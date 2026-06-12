# NYC Taxi Dataset — ClickHouse Exploration Notes

## Database: `testdb`

### Tables

#### `trips` (MergeTree)
- **Rows**: ~2 million (1,999,657)
- **Compressed size**: 96 MB (~486 MB uncompressed)
- **Engine**: MergeTree, partitioned by `toYYYYMM(pickup_date)`, ordered by `pickup_datetime`
- **Cab types**: yellow, green, uber

Key columns:
| Column | Type | Notes |
|---|---|---|
| `trip_id` | UInt32 | |
| `vendor_id` | Enum8 | |
| `pickup_datetime` / `dropoff_datetime` | DateTime | |
| `passenger_count` | UInt8 | |
| `trip_distance` | Float64 | |
| `fare_amount`, `tip_amount`, `total_amount` | Float32 | |
| `payment_type` | Enum8 | UNK, CSH, CRE, NOC, DIS |
| `pickup_latitude` / `pickup_longitude` | Float64 | Raw GPS coords |
| `pickup_ntaname` / `dropoff_ntaname` | String | Neighborhood name (190 distinct) |
| `pickup_boroct2010` / `dropoff_boroct2010` | String | Borough + census tract (1,687 distinct) |
| `pickup_puma` | UInt16 | Public Use Microdata Area (56 distinct) |
| `pickup` / `dropoff` | FixedString(25) | Binary-encoded zone ID — not yet decoded |

#### `taxi_zone_dictionary` (Dictionary)
- Sourced from S3 CSV: `datasets-documentation.s3.eu-west-3.amazonaws.com/nyc-taxi/taxi_zone_lookup.csv`
- Columns: `LocationID` (UInt16), `Borough`, `Zone`, `service_zone`
- Useful for joining against the binary `pickup` / `dropoff` columns (TODO: decode mapping)

---

## Pickup Location Granularity

From coarsest to finest:

| Level | Field | Distinct Values |
|---|---|---|
| Borough | `pickup_borocode` | 6 |
| PUMA | `pickup_puma` | 56 |
| Neighborhood (NTA) | `pickup_ntaname` | 190 |
| Borough + Census Tract | `pickup_boroct2010` | 1,687 |
| GPS ~11m precision | `pickup_latitude` (4 d.p.) | 3,105 |
| GPS ~10cm precision | `pickup_latitude` (6 d.p.) | 47,492 |

---

## Top Pickup Neighborhoods

| Rank | Neighborhood | Trips |
|---|---|---|
| 1 | Midtown-Midtown South | 351,722 |
| 2 | Hudson Yards-Chelsea-Flatiron-Union Square | 192,086 |
| 3 | West Village | 140,390 |
| 4 | Turtle Bay-East Midtown | 131,659 |
| 5 | Upper East Side-Carnegie Hill | 122,928 |
| 6 | Airport | 100,803 |
| 7 | SoHo-TriBeCa-Civic Center-Little Italy | 96,631 |
| 8 | Murray Hill-Kips Bay | 92,441 |
| 9 | Upper West Side | 90,139 |
| 10 | Clinton | 86,634 |

---

## OSM Data (NYC Extract)

To support reverse geocoding the 47k distinct GPS pickup points.

| File | Size | Location |
|---|---|---|
| `new-york-latest.osm.pbf` | 468 MB | `~/Downloads/` |
| `nyc-latest.osm.pbf` | 92 MB | `~/Downloads/` |

### How the extract was made

```bash
# Install osmium
brew install osmium-tool

# Download NY state PBF from Geofabrik
curl -L -o new-york-latest.osm.pbf https://download.geofabrik.de/north-america/us/new-york-latest.osm.pbf

# Crop to NYC 5 boroughs bounding box
osmium extract --bbox=-74.2591,40.4774,-73.7004,40.9176 \
  new-york-latest.osm.pbf -o nyc-latest.osm.pbf
```

### Next steps (not yet done)
- Load `nyc-latest.osm.pbf` into ClickHouse via `osmium export` → CSV → ClickHouse
- Or run a local Nominatim instance for reverse geocoding
- Or decode the binary `pickup` column and join to `taxi_zone_dictionary` (simpler, no OSM needed)
