#!/usr/bin/env bash
# Put the cluster back to the starting state (helm/values.yaml: 2x2, 24.8, 1 GB)
# between rehearsals without recreating the cluster. Data is dropped and reloaded.
source "$(dirname "$0")/lib.sh"
bold "Resetting release '$RELEASE' to helm/values.yaml"
ch -q "DROP DATABASE IF EXISTS demo ON CLUSTER $CLUSTER SYNC" || true
# -f without --reuse-values discards every --set made during the demo.
show helm upgrade "$RELEASE" "$CHART" ${CHART_VERSION_ARGS[@]+"${CHART_VERSION_ARGS[@]}"} -n "$NS" -f "$VALUES"
wait_chi 1800
"$(dirname "$0")/03-load-data.sh"
