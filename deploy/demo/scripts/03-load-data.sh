#!/usr/bin/env bash
# Create replicated + distributed tables and load NYC taxi trips from S3.
# TAXI_FILES picks which of the 20 public files (0..19, ~1M trips each) to load.
source "$(dirname "$0")/lib.sh"
TAXI_FILES="${TAXI_FILES:-0..2}"
bold "Creating schema ON CLUSTER"
ch --multiquery < "$DEMO_DIR/sql/schema.sql"
bold "Loading NYC taxi files trips_{$TAXI_FILES}.gz through the Distributed table"
time (sed "s/__FILES__/$TAXI_FILES/g" "$DEMO_DIR/sql/load.sql" | ch --multiquery)
ch -q "SELECT _shard_num AS shard, formatReadableQuantity(count()) AS trips FROM demo.trips GROUP BY shard ORDER BY shard FORMAT PrettyCompact"
