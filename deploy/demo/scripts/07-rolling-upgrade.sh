#!/usr/bin/env bash
# Upgrade ClickHouse by changing the image tag with `helm upgrade`. The operator
# rolls one host at a time, waiting for each to rejoin before moving on. Keep
# watch-availability.sh running in another terminal while this runs.
source "$(dirname "$0")/lib.sh"
TO="${1:-$UPGRADE_TAG}"
bold "Versions before"
ch -q "SELECT hostName(), version() FROM clusterAllReplicas($CLUSTER, system.one) ORDER BY 1 FORMAT PrettyCompact"
bold "Rolling upgrade -> clickhouse-server:$TO"
helm_upgrade --set-string image.tag="$TO"
wait_chi 1800
bold "Versions after"
ch -q "SELECT hostName(), version() FROM clusterAllReplicas($CLUSTER, system.one) ORDER BY 1 FORMAT PrettyCompact"
show helm history "$RELEASE" -n "$NS"
