#!/usr/bin/env bash
# Optional: Prometheus + Grafana with the operator's ServiceMonitors and dashboards.
# Needs ~2 GB extra memory. Turns them on in the separately installed operator release.
source "$(dirname "$0")/lib.sh"
bold "Installing kube-prometheus-stack"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update prometheus-community >/dev/null
show helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace --wait \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.sidecar.dashboards.enabled=true \
  --set grafana.sidecar.dashboards.searchNamespace=ALL
# The operator is its own Helm release (see SETUP.md), so turn these on there, not on "demo".
show helm upgrade "$OPERATOR_RELEASE" "$OPERATOR_CHART" -n "${OPERATOR_NS:-clickhouse-operator}" \
  --reuse-values --set serviceMonitor.enabled=true --set dashboards.enabled=true
echo
echo "Grafana:  kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80"
echo "Password: kubectl -n monitoring get secret monitoring-grafana -o jsonpath='{.data.admin-password}' | base64 -d"
