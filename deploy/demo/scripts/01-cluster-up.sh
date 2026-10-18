#!/usr/bin/env bash
# Create a 3-node minikube cluster and pretend each node is its own zone.
# Sizing is per node: MINIKUBE_MEMORY (default 3g) x MINIKUBE_NODES (default 3).
source "$(dirname "$0")/lib.sh"
NODES="${MINIKUBE_NODES:-3}"
bold "Starting minikube profile '$CLUSTER_NAME' ($NODES nodes)"
if ! minikube status -p "$CLUSTER_NAME" >/dev/null 2>&1; then
  driver=()
  [[ -n "${MINIKUBE_DRIVER:-}" ]] && driver=(--driver "$MINIKUBE_DRIVER")
  show minikube start -p "$CLUSTER_NAME" --nodes "$NODES" \
    --cpus "${MINIKUBE_CPUS:-2}" --memory "${MINIKUBE_MEMORY:-3g}" \
    --kubernetes-version "${K8S_VERSION:-v1.31.0}" "${driver[@]}"
fi
kubectl config use-context "$CLUSTER_NAME" >/dev/null

# minikube's built-in hostpath provisioner doesn't pin volumes to a node, so on a
# multi-node cluster a restarted pod can come back to an empty disk. Use
# local-path-provisioner instead: each PV is bound to the node its pod first
# ran on, which is how real local SSDs behave (and what the chaos step shows).
bold "Installing local-path-provisioner as the default StorageClass"
minikube addons disable default-storageclass -p "$CLUSTER_NAME" >/dev/null 2>&1 || true
kubectl apply -f "https://raw.githubusercontent.com/rancher/local-path-provisioner/${LOCAL_PATH_VERSION:-v0.0.30}/deploy/local-path-storage.yaml" >/dev/null
kubectl patch storageclass local-path \
  -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}' >/dev/null
kubectl annotate --overwrite storageclass standard storageclass.kubernetes.io/is-default-class=false >/dev/null 2>&1 || true
kubectl -n local-path-storage rollout status deploy/local-path-provisioner --timeout=120s

zones=(zone-a zone-b zone-c); i=0
for node in $(kubectl get nodes -o name); do
  kubectl label --overwrite "$node" topology.kubernetes.io/zone="${zones[$((i % 3))]}" >/dev/null
  i=$((i + 1))
done
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
show kubectl get nodes -L topology.kubernetes.io/zone
show kubectl get storageclass

if [[ "${PRELOAD_IMAGES:-1}" == "1" ]]; then
  bold "Pre-loading images into every minikube node (saves minutes on stage)"
  for img in clickhouse/clickhouse-server:24.8 "clickhouse/clickhouse-server:${UPGRADE_TAG}" \
             clickhouse/clickhouse-keeper:24.8; do
    minikube image load "$img" -p "$CLUSTER_NAME" || echo "  skipped $img"
  done
fi
