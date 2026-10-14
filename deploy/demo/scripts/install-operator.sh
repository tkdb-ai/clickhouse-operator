#!/usr/bin/env bash
# Install the Altinity operator from this repo (deploy/helm/clickhouse-operator)
# as its own release, watching only the demo namespace. The demo itself assumes
# the operator is already there; this is the once-per-cluster setup step.
# Per the chart README, Keeper never comes up when the operator is cluster-wide.
source "$(dirname "$0")/lib.sh"
op_ns="${OPERATOR_NS:-clickhouse-operator}"
bold "Installing the operator ($OPERATOR_CHART) as '$OPERATOR_RELEASE' in $op_ns, watching $NS"
show helm upgrade --install "$OPERATOR_RELEASE" "$OPERATOR_CHART" -n "$op_ns" --create-namespace \
  --set "watchNamespaces={$NS}" --wait --timeout 5m
show kubectl get crd clickhouseinstallations.clickhouse.altinity.com clickhousekeeperinstallations.clickhouse-keeper.altinity.com
show kubectl -n "$op_ns" get pods
