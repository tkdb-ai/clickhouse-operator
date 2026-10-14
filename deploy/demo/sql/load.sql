-- NYC taxi trips from the public ClickHouse docs bucket: 20 files, trips_0 to
-- trips_19, about 1M rows (82 MB gzipped) each. __FILES__ is a glob range such
-- as 0..2. ClickHouse reads straight from S3, nothing goes through the laptop.
-- The source labels card and cash backwards (the "CSH" rows carry the tips, as
-- only card tips are recorded by TLC), so the two are swapped back on load.
INSERT INTO demo.trips
SELECT
    trip_id, pickup_datetime, dropoff_datetime,
    pickup_longitude, pickup_latitude, dropoff_longitude, dropoff_latitude,
    passenger_count, trip_distance, fare_amount, extra, tip_amount,
    tolls_amount, total_amount,
    transform(payment_type, ['CSH', 'CRE'], ['CRE', 'CSH'], payment_type) AS payment_type,
    pickup_ntaname, dropoff_ntaname
FROM s3('https://datasets-documentation.s3.eu-west-3.amazonaws.com/nyc-taxi/trips_{__FILES__}.gz', 'TabSeparatedWithNames')
SETTINGS input_format_try_infer_datetimes = 0, insert_distributed_sync = 1;
