# Monitoring Setup

ClickHouse exposes a Prometheus-compatible metrics endpoint. This guide covers two ways to set up monitoring.

## Option A: Helm Chart (recommended)

The `clickhouse-helm-chart` handles everything automatically when `monitoring.enabled=true` (the default):

- Injects a `prometheus.xml` config file that enables the `/metrics` endpoint on port `9363`
- Adds pod scrape annotations so Prometheus auto-discovers ClickHouse pods

### Deploy Prometheus

```bash
# Deploy Prometheus into the same namespace as ClickHouse
PROMETHEUS_NAMESPACE=clickstack NO_WAIT=1 \
  bash deploy/prometheus/create-prometheus.sh
```

### Deploy Grafana

```bash
helm repo add grafana https://grafana.github.io/helm-charts && helm repo update

helm install grafana grafana/grafana -n clickstack \
  --set adminPassword="$(kubectl get secret ch1-clickhouse-installation-admin \
    -n clickstack -o jsonpath='{.data.admin}' | base64 -d)" \
  --set "datasources.datasources\\.yaml.apiVersion=1" \
  --set "datasources.datasources\\.yaml.datasources[0].name=Prometheus" \
  --set "datasources.datasources\\.yaml.datasources[0].type=prometheus" \
  --set "datasources.datasources\\.yaml.datasources[0].url=http://prometheus:9090" \
  --set "datasources.datasources\\.yaml.datasources[0].isDefault=true"
```

Access Grafana (login: `admin` / your ClickHouse admin password):

```bash
kubectl port-forward -n clickstack svc/grafana 3000:80
# Open http://localhost:3000
```

### Verify metrics are being scraped

```bash
# Confirm ClickHouse pods have scrape annotations
kubectl get pods -n clickstack -l clickhouse.altinity.com/chi=ch1-clickhouse-installation \
  -o jsonpath='{.items[0].metadata.annotations}' | python3 -m json.tool

# Hit the metrics endpoint directly
kubectl exec -n clickstack chi-ch1-clickhouse-installation-main-0-0-0 -c clickhouse \
  -- curl -s http://localhost:9363/metrics | head -20
```

---

## Option B: Manual Setup

For custom Prometheus/Grafana installations see the detailed per-component guides:

1. [Prometheus setup](./prometheus_setup.md)
2. [Grafana setup](./grafana_setup.md)
