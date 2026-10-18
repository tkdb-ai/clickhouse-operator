#!/usr/bin/env bash
# Self-healing: delete a ClickHouse pod. The StatefulSet recreates it, the same
# PVC is re-attached, and the replica catches up from Keeper.
source "$(dirname "$0")/lib.sh"
POD="${1:-chi-$CHI-$CLUSTER-0-0-0}"
before=$(ch -q "SELECT count() FROM demo.trips")
bold "Rows before: $before. Deleting pod $POD"
show k delete pod "$POD" --wait=false
show k get pods -l clickhouse.altinity.com/chi="$CHI"
echo "Queries still succeed (served by the other replica of shard 0):"
ch -q "SELECT count() FROM demo.trips"
k wait --for=condition=Ready "pod/$POD" --timeout=300s 2>/dev/null || { sleep 10; k wait --for=condition=Ready "pod/$POD" --timeout=300s; }
after=$(ch -q "SELECT count() FROM demo.trips")
bold "Pod is back. Rows after: $after"
show k get pvc -l clickhouse.altinity.com/chi="$CHI"
[[ "$before" == "$after" ]] && echo "No data lost." || echo "Row count differs (inserts during the test?)"
