#!/usr/bin/env bash
# Shared helpers for the demo scripts. Source, don't execute.
set -euo pipefail

export NS="${NS:-ch-demo}"
export CLUSTER_NAME="${CLUSTER_NAME:-ch-demo}"
# Helm release of the local "clickhouse-installation" chart (values.yaml sets
# fullnameOverride: demo, so the CHI is "demo" and the CHK "demo-keeper").
# The chart always names the ClickHouse cluster "main".
export RELEASE="${RELEASE:-demo}"
DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DEMO_DIR
# Both charts live in this repo under deploy/helm.
export CHART="${CHART:-$DEMO_DIR/../helm/clickhouse-helm-chart}"
export OPERATOR_CHART="${OPERATOR_CHART:-$DEMO_DIR/../helm/clickhouse-operator}"
# Empty for a local chart directory; set it only if CHART points at a repo chart.
export CHART_VERSION="${CHART_VERSION:-}"
export CHI="${CHI:-demo}"
export CLUSTER="${CLUSTER:-main}"
export KEEPER_CHK="${KEEPER_CHK:-$CHI-keeper}"
# The operator is installed separately (not by this chart); where it runs.
export OPERATOR_NS="${OPERATOR_NS:-}"   # blank = find it by its pod label
export OPERATOR_RELEASE="${OPERATOR_RELEASE:-clickhouse-operator}"
export UPGRADE_TAG="${UPGRADE_TAG:-25.3}"
export VALUES="${VALUES:-$DEMO_DIR/helm/values.yaml}"
# --version only makes sense for a repo chart. (The odd expansion below keeps an
# empty array safe under `set -u` in macOS bash 3.2.)
CHART_VERSION_ARGS=(); [[ -n "$CHART_VERSION" ]] && CHART_VERSION_ARGS=(--version "$CHART_VERSION")

bold()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
show()  { printf '\033[0;33m$ %s\033[0m\n' "$*"; "$@"; }   # echo then run

k() { kubectl -n "$NS" "$@"; }

# Run SQL from the client pod through the load-balanced CHI Service.
ch() {
  k exec -i ch-client -- clickhouse-client \
    --host "clickhouse-$CHI" --user demo --password demo "$@"
}

# Run SQL inside a specific ClickHouse pod (default user, localhost).
ch_pod() {
  local pod="$1"; shift
  k exec -i "$pod" -c clickhouse -- clickhouse-client "$@"
}

chi_status() {
  k get chi "$CHI" -o jsonpath='{.status.status}' 2>/dev/null || true
}

# Block until the operator reports the CHI as Completed and all pods are Ready.
wait_chi() {
  local timeout="${1:-600}" start=$SECONDS
  bold "Waiting for chi/$CHI to reconcile (timeout ${timeout}s)"
  # First give the operator up to 30s to pick the change up (status leaves Completed)...
  for _ in $(seq 1 15); do [[ "$(chi_status)" != "Completed" ]] && break; sleep 2; done
  # ...then wait for it to finish.
  until [[ "$(chi_status)" == "Completed" ]]; do
    (( SECONDS - start > timeout )) && { echo "timed out; status=$(chi_status)"; return 1; }
    printf '  status=%-12s pods=%s\n' "$(chi_status)" \
      "$(k get pods -l clickhouse.altinity.com/chi="$CHI" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
    sleep 5
  done
  k wait --for=condition=Ready pod -l clickhouse.altinity.com/chi="$CHI" --timeout=300s
}

ch_pods() { k get pods -l clickhouse.altinity.com/chi="$CHI" -o jsonpath='{.items[*].metadata.name}'; }

# One demo step = one `helm upgrade` that changes a value on top of the last
# release (--reuse-values). Shown on screen so the audience sees the whole change.
helm_upgrade() {
  show helm upgrade "$RELEASE" "$CHART" ${CHART_VERSION_ARGS[@]+"${CHART_VERSION_ARGS[@]}"} -n "$NS" --reuse-values "$@"
}

# Print max_memory_usage as each pod sees it. Ask each pod directly: through a
# Distributed query the initiator's settings would be forwarded to every shard.
per_pod_setting() {
  for p in $(ch_pods); do
    printf '%-26s max_memory_usage=%s\n' "$p" "$(ch_pod "$p" -q "SELECT getSetting('max_memory_usage')")"
  done
}

# Wait until every pod reports max_memory_usage = $1 (kubelet projects the new
# ConfigMap, then ClickHouse reloads users.d by itself).
wait_setting() {
  local want="$1" vals
  for _ in $(seq 1 40); do
    vals=$(for p in $(ch_pods); do ch_pod "$p" -q "SELECT getSetting('max_memory_usage')"; done | sort -u)
    [[ "$vals" == "$want" ]] && return 0
    printf '  current: %s\n' "${vals//$'\n'/ }"; sleep 3
  done
  echo "still not $want everywhere"; return 1
}

pod_ages() {
  k get pods -l clickhouse.altinity.com/chi="$CHI" \
    -o custom-columns=POD:.metadata.name,STARTED:.status.startTime,RESTARTS:.status.containerStatuses[0].restartCount
}
