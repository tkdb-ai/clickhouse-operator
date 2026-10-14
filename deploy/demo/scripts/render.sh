#!/usr/bin/env bash
# Show what Helm hands the operator: the ClickHouseInstallation and
# ClickHouseKeeperInstallation rendered from helm/values.yaml. No cluster needed.
source "$(dirname "$0")/lib.sh"
helm template "$RELEASE" "$CHART" ${CHART_VERSION_ARGS[@]+"${CHART_VERSION_ARGS[@]}"} -n "$NS" -f "$VALUES" "$@"
