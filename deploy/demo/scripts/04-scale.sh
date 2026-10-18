#!/usr/bin/env bash
# Scale shards or replicas by changing ONE value with `helm upgrade`.
# Usage: 04-scale.sh shards 3   |   04-scale.sh replicas 3
source "$(dirname "$0")/lib.sh"
what="${1:?shards|replicas}"; n="${2:?count}"
case "$what" in
  shards)   key=layout.shardsCount ;;
  replicas) key=layout.replicasCount ;;
  *) echo "usage: $0 shards|replicas N"; exit 2 ;;
esac
bold "Before"
ch -q "SELECT shard_num, replica_num, host_name FROM system.clusters WHERE cluster='$CLUSTER' FORMAT PrettyCompact"
bold "Scaling $what -> $n"
helm_upgrade --set "$key=$n"
wait_chi 900
bold "After: the operator created pods/PVCs, updated remote_servers, and copied the schema"
show k get pods -l clickhouse.altinity.com/chi="$CHI" -o wide
ch -q "SELECT shard_num, replica_num, host_name FROM system.clusters WHERE cluster='$CLUSTER' FORMAT PrettyCompact"
ch -q "SELECT getMacro('shard') AS shard, getMacro('replica') AS replica, count() AS rows
       FROM clusterAllReplicas($CLUSTER, demo.trips_local) GROUP BY shard, replica ORDER BY shard, replica
       FORMAT PrettyCompact"
if [[ "$what" == "shards" ]]; then
  cat <<'NOTE'
Note: the new shard starts EMPTY. ClickHouse does not rebalance existing data;
new inserts are spread across all shards from now on. Talk track: rebalance by
re-inserting (INSERT ... SELECT) or by giving the new shard a higher weight.
NOTE
  if [[ "${OFFLINE:-0}" == "1" ]]; then
    bold "Offline: re-insert 2M existing trips under new ids, watch them land on the new shard too"
    ch -q "INSERT INTO demo.trips SELECT * REPLACE (toUInt32(trip_id + 2000000000) AS trip_id)
           FROM demo.trips WHERE trip_id < 2000000000 LIMIT 2000000 SETTINGS insert_distributed_sync = 1"
  else
    bold "Load two more taxi files (~2M trips): watch them land on the new shard too"
    sed "s/__FILES__/${EXTRA_TAXI_FILES:-3..4}/g" "$DEMO_DIR/sql/load.sql" | ch --multiquery
  fi
  ch -q "SELECT _shard_num AS shard, count() AS rows FROM demo.trips GROUP BY shard ORDER BY shard FORMAT PrettyCompact"
else
  echo "New replicas fetched every part from their peers via Keeper; row counts match."
fi
