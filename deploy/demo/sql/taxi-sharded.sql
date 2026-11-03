-- Sharded + replicated version of the taxi database, including the geo tables.
-- Run once against any node:
--   clickhouse-client --user <u> --password <p> --multiquery < taxi-sharded.sql
-- ON CLUSTER fans the DDL out through Keeper. {cluster}, {shard} and {replica}
-- are macros the operator writes into every pod.
-- Same layout as schema.sql, but in `taxi` and with the zone/borough lookups.

CREATE DATABASE IF NOT EXISTS taxi ON CLUSTER '{cluster}';

-- Optional: if an old single-node taxi.trips already exists, move it aside
-- first (this table name is reused for the Distributed table below), then copy
-- the rows back in after step 3. Run these two statements on the node that
-- holds the data, not ON CLUSTER.
--   RENAME TABLE taxi.trips TO taxi.trips_old;
--   INSERT INTO taxi.trips SELECT * FROM taxi.trips_old SETTINGS insert_distributed_sync = 1;
--   DROP TABLE taxi.trips_old;   -- once the counts match

-- 1. Local table: each shard holds its own slice, replicas inside a shard stay
--    in sync. Never query this directly for full results.
CREATE TABLE IF NOT EXISTS taxi.trips_local ON CLUSTER '{cluster}'
(
    trip_id             UInt32,
    pickup_datetime     DateTime,
    dropoff_datetime    DateTime,
    pickup_longitude    Nullable(Float64),
    pickup_latitude     Nullable(Float64),
    dropoff_longitude   Nullable(Float64),
    dropoff_latitude    Nullable(Float64),
    passenger_count     UInt8,
    trip_distance       Float32,
    fare_amount         Float32,
    extra               Float32,
    tip_amount          Float32,
    tolls_amount        Float32,
    total_amount        Float32,
    payment_type        Enum('CSH' = 1, 'CRE' = 2, 'NOC' = 3, 'DIS' = 4, 'UNK' = 5),
    pickup_ntaname      LowCardinality(String),
    dropoff_ntaname     LowCardinality(String)
)
ENGINE = ReplicatedMergeTree('/clickhouse/tables/{shard}/{database}/{table}', '{replica}')
PARTITION BY toYYYYMM(pickup_datetime)
ORDER BY (pickup_datetime, dropoff_datetime);

-- 2. The table people query and insert into. Rows are routed to a shard by
--    trip_id, so the spread is even and a given trip always lands on one shard.
CREATE TABLE IF NOT EXISTS taxi.trips ON CLUSTER '{cluster}' AS taxi.trips_local
ENGINE = Distributed('{cluster}', taxi, trips_local, cityHash64(trip_id));

-- 3. Lookup tables. These are small and every shard needs the full set, so the
--    Keeper path has no {shard}: all pods are replicas of ONE table. A single
--    INSERT then reaches every node.
CREATE TABLE IF NOT EXISTS taxi.taxi_zones ON CLUSTER '{cluster}'
(
    location_id UInt16,
    borough     LowCardinality(String),
    zone        String,
    geometry    MultiPolygon
)
ENGINE = ReplicatedMergeTree('/clickhouse/tables/{database}/{table}', '{replica}')
ORDER BY location_id;

CREATE TABLE IF NOT EXISTS taxi.boroughs ON CLUSTER '{cluster}'
(
    borough_code UInt8,
    borough_name LowCardinality(String),
    geometry     MultiPolygon
)
ENGINE = ReplicatedMergeTree('/clickhouse/tables/{database}/{table}', '{replica}')
ORDER BY borough_code;

-- 4. Polygon dictionaries (used with dictGet(..., (lon, lat))). Each node builds
--    its own copy from its local lookup table. LIFETIME(0) means no automatic
--    refresh, so reload after loading or changing the lookup tables.
CREATE DICTIONARY IF NOT EXISTS taxi.zone_dict ON CLUSTER '{cluster}'
(
    geometry    MultiPolygon,
    location_id UInt16,
    zone        String,
    borough     String
)
PRIMARY KEY geometry
SOURCE(CLICKHOUSE(DB 'taxi' TABLE 'taxi_zones'))
LIFETIME(0)
LAYOUT(POLYGON(STORE_POLYGON_KEY_COLUMN 1));

CREATE DICTIONARY IF NOT EXISTS taxi.borough_dict ON CLUSTER '{cluster}'
(
    geometry     MultiPolygon,
    borough_name String
)
PRIMARY KEY geometry
SOURCE(CLICKHOUSE(DB 'taxi' TABLE 'boroughs'))
LIFETIME(0)
LAYOUT(POLYGON(STORE_POLYGON_KEY_COLUMN 1));

-- 5. After loading data, run these to check it landed everywhere.
--    Load trips with INSERT INTO taxi.trips (the Distributed table).
--    Load zones/boroughs with a normal INSERT on any one node.
--
-- Rows per replica (expect an even split between shards, equal inside a shard):
--   SELECT hostName() AS host, count() FROM clusterAllReplicas('{cluster}', taxi.trips_local) GROUP BY host ORDER BY host;
-- Total through the Distributed table:
--   SELECT count() FROM taxi.trips;
-- Lookup rows on every node (expect the same number everywhere):
--   SELECT hostName(), count() FROM clusterAllReplicas('{cluster}', taxi.taxi_zones) GROUP BY 1;
-- Refresh dictionaries after loading zones:
--   SYSTEM RELOAD DICTIONARY ON CLUSTER '{cluster}' taxi.zone_dict;
--   SYSTEM RELOAD DICTIONARY ON CLUSTER '{cluster}' taxi.borough_dict;
