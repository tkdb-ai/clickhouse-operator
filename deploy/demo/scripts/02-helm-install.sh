#!/usr/bin/env bash
# One `helm install` of the local clickhouse-installation chart brings up a
# 3-node Keeper and 2 shards x 2 replicas, all from helm/values.yaml. The Altinity
# operator is assumed to be installed already; this checks it before installing.
source "$(dirname "$0")/lib.sh"
[[ -d "$CHART" ]] || { echo "chart not found at $CHART (set CHART=...)"; exit 1; }

bold "Checking the Altinity operator is installed and watches namespace $NS"
for crd in clickhouseinstallations.clickhouse.altinity.com clickhousekeeperinstallations.clickhouse-keeper.altinity.com; do
  kubectl get crd "$crd" >/dev/null 2>&1 || { echo "  missing CRD $crd: install the operator first"; exit 1; }
done
# Helm installs label the pod app.kubernetes.io/name=altinity-clickhouse-operator;
# the plain-manifest install labels it app=clickhouse-operator.
op_sel=""
for sel in app.kubernetes.io/name=altinity-clickhouse-operator app=clickhouse-operator; do
  op_ns="${OPERATOR_NS:-$(kubectl get pods -A -l "$sel" -o jsonpath='{.items[0].metadata.namespace}' 2>/dev/null || true)}"
  [[ -n "$op_ns" ]] && kubectl -n "$op_ns" get pods -l "$sel" --no-headers 2>/dev/null | grep -q . && { op_sel="$sel"; break; }
done
[[ -n "$op_sel" ]] || { echo "  no clickhouse-operator pod found (set OPERATOR_NS=...)"; exit 1; }
kubectl -n "$op_ns" wait --for=condition=Ready pod -l "$op_sel" --timeout=120s
# The operator chart writes watchNamespaces into config.yaml (watch.namespaces.include);
# empty means "only its own namespace" (all namespaces when it runs in kube-system).
echo "  operator runs in namespace $op_ns; its watch config:"
kubectl -n "$op_ns" get configmap -l "$op_sel" -o jsonpath='{range .items[*]}{.data.config\.yaml}{end}' 2>/dev/null \
  | awk '/^watch:/{p=1} p&&/^[^ #w]/{p=0} p' | sed 's/^/    /'
bold "Installing release '$RELEASE' ($CHART) from helm/values.yaml"
show helm upgrade --install "$RELEASE" "$CHART" ${CHART_VERSION_ARGS[@]+"${CHART_VERSION_ARGS[@]}"} \
  -n "$NS" --create-namespace -f "$VALUES" --wait --timeout 10m
bold "Waiting for ClickHouse Keeper (3 nodes)"
# If the operator doesn't watch $NS (or runs cluster-wide, which the chart README
# says breaks Keeper), the CHK never gets pods: fail with a hint instead of hanging.
for i in $(seq 1 60); do
  [[ "$(k get pods -l clickhouse-keeper.altinity.com/chk="$KEEPER_CHK" --no-headers 2>/dev/null | wc -l)" -ge 3 ]] && break
  (( i == 60 )) && { echo "no Keeper pods after 3 min: check the operator watches namespace $NS (operator.watchNamespaces)"; exit 1; }
  sleep 3
done
k wait --for=condition=Ready pod -l clickhouse-keeper.altinity.com/chk="$KEEPER_CHK" --timeout=300s
for p in $(k get pods -l clickhouse-keeper.altinity.com/chk="$KEEPER_CHK" -o name); do
  printf '%s: ' "$p"
  k exec "$p" -- bash -c 'echo mntr | (exec 3<>/dev/tcp/127.0.0.1/2181; cat >&3; cat <&3)' 2>/dev/null | grep zk_server_state || echo "?"
done
wait_chi 900
k apply -f "$DEMO_DIR/manifests/client.yaml"
k wait --for=condition=Ready pod/ch-client --timeout=120s
bold "What Helm and the operator built from one values file"
show helm list -n "$NS"
show k get chi,chk,sts,pvc,svc -n "$NS"
show k get pods -l clickhouse.altinity.com/chi="$CHI" -o wide
bold "ClickHouse's own view of the cluster"
ch -q "SELECT cluster, shard_num, replica_num, host_name FROM system.clusters WHERE cluster='$CLUSTER' FORMAT PrettyCompact"
