-- 1. When does New York take cabs? Trips and average fare by hour of day
SELECT toHour(pickup_datetime) AS hour, count() AS trips, round(avg(fare_amount), 2) AS avg_fare
FROM demo.trips
GROUP BY hour
ORDER BY hour;

-- 2. Busiest pickup neighborhoods
SELECT pickup_ntaname AS neighborhood, count() AS trips, round(avg(trip_distance), 2) AS avg_miles
FROM demo.trips
WHERE pickup_ntaname != ''
GROUP BY neighborhood
ORDER BY trips DESC
LIMIT 10;

-- 3. Who tips? Average tip as a percent of fare, by payment type
SELECT payment_type, count() AS trips, round(avg(tip_amount / nullIf(fare_amount, 0)) * 100, 1) AS tip_pct
FROM demo.trips
GROUP BY payment_type
ORDER BY trips DESC;

-- 4. Bigger groups, longer rides? Distance and fare by passenger count
SELECT passenger_count, count() AS trips, round(avg(trip_distance), 2) AS avg_miles, round(avg(total_amount), 2) AS avg_total
FROM demo.trips
WHERE passenger_count BETWEEN 1 AND 6
GROUP BY passenger_count
ORDER BY passenger_count;

-- 5. Where does the data physically live? Rows per shard...
SELECT _shard_num AS shard, count() AS rows
FROM demo.trips
GROUP BY shard
ORDER BY shard;

-- 6. ...and per replica (every replica of a shard should match)
SELECT getMacro('shard') AS shard, getMacro('replica') AS replica, count() AS rows
FROM clusterAllReplicas(main, demo.trips_local)
GROUP BY shard, replica
ORDER BY shard, replica;
