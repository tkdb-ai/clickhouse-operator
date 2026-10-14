-- Run once against any node. ON CLUSTER fans the DDL out through Keeper.
-- {shard} and {replica} are macros the operator writes into every pod.
-- Schema follows the ClickHouse docs' NYC taxi example (2009-2015 trips).
CREATE DATABASE IF NOT EXISTS demo ON CLUSTER main;

CREATE TABLE IF NOT EXISTS demo.trips_local ON CLUSTER main
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

-- The table people query. Rows are routed to shards by trip_id.
CREATE TABLE IF NOT EXISTS demo.trips ON CLUSTER main AS demo.trips_local
ENGINE = Distributed(main, demo, trips_local, cityHash64(trip_id));
