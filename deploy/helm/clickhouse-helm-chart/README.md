# ClickHouse Installation Helm Chart

Deploys a `ClickHouseInstallation` (CHI) custom resource managed by the [Altinity ClickHouse Operator](https://github.com/Altinity/clickhouse-operator). The operator must be installed in the cluster before this chart will work — it is not included here.

## Prerequisites

- Kubernetes 1.21+
- Helm 3.x
- [Altinity ClickHouse Operator](https://github.com/Altinity/clickhouse-operator) installed

## Quick Start

```bash
helm install my-ch . -n clickstack --create-namespace
```

Retrieve the generated admin password:
```bash
kubectl get secret my-ch-clickhouse-installation-admin -n clickstack \
  -o jsonpath='{.data.admin}' | base64 --decode
```

> **Looking for what the database can *do* and how to use each capability**
> (connecting, sharding/replication, S3 tiered storage, backups, monitoring, …)?
> See **[FEATURES.md](FEATURES.md)**. This README is the value-by-value
> configuration reference.

---

## Configuration Reference

### Identity

| Value | Default | Description |
|---|---|---|
| `nameOverride` | `""` | Override the chart name |
| `fullnameOverride` | `""` | Override the fully qualified release name |

---

### Cluster Layout

| Value | Default | Description |
|---|---|---|
| `layout.shardsCount` | `1` | Number of shards |
| `layout.replicasCount` | `2` | Number of replicas per shard |

Replication requires a coordination service (`coordination.mode: keeper` or `zookeeper`). For a single standalone node, set `replicasCount: 1` and `coordination.mode: none`.

---

### ClickHouse Image

| Value | Default | Description |
|---|---|---|
| `image.repository` | `clickhouse/clickhouse-server` | Container image |
| `image.tag` | `"24.8"` | Image tag (falls back to `appVersion` if unset) |
| `image.pullPolicy` | `IfNotPresent` | Image pull policy |

---

### Storage

| Value | Default | Description |
|---|---|---|
| `storage.data.size` | `10Gi` | Data PVC size |
| `storage.data.storageClassName` | `hostpath` | Storage class — change for your cluster |
| `storage.data.accessModes` | `[ReadWriteOnce]` | PVC access modes |
| `storage.log.enabled` | `false` | Create a separate PVC for ClickHouse logs |
| `storage.log.size` | `2Gi` | Log PVC size |
| `storage.log.storageClassName` | `standard` | Storage class for log PVC |
| `storage.log.accessModes` | `[ReadWriteOnce]` | PVC access modes |

---

### Coordination

Controls how ClickHouse replicas coordinate with each other. Required for replication and distributed DDL.

| Value | Default | Description |
|---|---|---|
| `coordination.mode` | `keeper` | `keeper`, `zookeeper`, or `none` |

#### `keeper` mode (recommended)

Deploys a `ClickHouseKeeperInstallation` (CHK) managed by the same operator — no external ZooKeeper required.

| Value | Default | Description |
|---|---|---|
| `coordination.keeper.replicasCount` | `1` | Number of Keeper replicas. Use `3` for production HA (must be odd) |
| `coordination.keeper.image.repository` | `clickhouse/clickhouse-keeper` | Keeper image |
| `coordination.keeper.image.tag` | `"24.8"` | Keeper image tag |
| `coordination.keeper.image.pullPolicy` | `IfNotPresent` | Pull policy |
| `coordination.keeper.storage.size` | `10Gi` | Keeper data PVC size |
| `coordination.keeper.storage.storageClassName` | `hostpath` | Storage class |
| `coordination.keeper.storage.accessModes` | `[ReadWriteOnce]` | PVC access modes |
| `coordination.keeper.resources` | `{}` | CPU/memory limits and requests |

Pod anti-affinity is automatically enabled when `replicasCount > 1` to spread Keeper pods across nodes.

#### `zookeeper` mode

Points ClickHouse at an existing external ZooKeeper ensemble.

| Value | Default | Description |
|---|---|---|
| `coordination.zookeeper.nodes` | `[{host: zookeeper.default.svc.cluster.local, port: 2181}]` | ZooKeeper node list |

#### `none` mode

Disables coordination entirely. Only suitable for single-node deployments with no replication.

---

### Users & Authentication

| Value | Default | Description |
|---|---|---|
| `adminPassword` | `""` | Admin password. Leave empty to auto-generate a random 16-character password |
| `users.default.password` | `"password"` | Password for the `default` user |
| `users.default.networks/ip` | `"0.0.0.0/0"` | Allowed source IPs for the `default` user |
| `users.admin.profile` | `default` | Profile assigned to the `admin` user |

The `admin` password is stored in a Kubernetes Secret named `<release>-clickhouse-installation-admin`. Helm's `lookup` function preserves the existing secret on `helm upgrade`, so the password never rotates unexpectedly.

Additional users can be added under `users`:
```yaml
users:
  myuser:
    password: "mypassword"
    networks/ip: "10.0.0.0/8"
    profile: default
```

---

### ClickHouse Configuration

These values map directly to ClickHouse's XML configuration.

| Value | Default | Description |
|---|---|---|
| `settings` | `compression/case/method: zstd` | Entries for `config.xml` (dot-path format) |
| `profiles` | `{}` | User profiles (e.g. `default/max_memory_usage: 1000000000`) |
| `quotas` | `{}` | Query quotas |
| `files` | `{}` | Custom XML config files mounted into ClickHouse |

**`settings` example:**
```yaml
settings:
  compression/case/method: zstd
  max_connections: "500"
  logger/level: information
```

**`files` example** (custom dictionary):
```yaml
files:
  dict1.xml: |
    <clickhouse>
      <dictionary>
        <!-- config -->
      </dictionary>
    </clickhouse>
```

---

### Resource Limits

| Value | Default | Description |
|---|---|---|
| `resources` | `{}` | CPU/memory limits and requests for the ClickHouse container |

```yaml
resources:
  limits:
    cpu: 2000m
    memory: 8Gi
  requests:
    cpu: 500m
    memory: 2Gi
```

---

### Monitoring

Enables a Prometheus-compatible metrics endpoint in ClickHouse. When enabled, a `prometheus.xml` config file is injected into ClickHouse and pod scrape annotations (`prometheus.io/scrape`, `prometheus.io/port`, `prometheus.io/path`) are added so a standard Prometheus installation auto-discovers the pods.

| Value | Default | Description |
|---|---|---|
| `monitoring.enabled` | `true` | Enable Prometheus metrics and pod scrape annotations |
| `monitoring.prometheus.enabled` | `true` | Inject `prometheus.xml` into ClickHouse config |
| `monitoring.prometheus.port` | `9363` | Metrics scrape port |
| `monitoring.serviceMonitor` | `false` | Create a `ServiceMonitor` for the Prometheus Operator |

Deploy Prometheus and Grafana alongside the chart:
```bash
# Prometheus (into the same namespace as ClickHouse)
PROMETHEUS_NAMESPACE=clickstack NO_WAIT=1 bash deploy/prometheus/create-prometheus.sh

# Grafana via Helm (Prometheus pre-wired as default datasource)
helm repo add grafana https://grafana.github.io/helm-charts && helm repo update
helm install grafana grafana/grafana -n clickstack \
  --set "datasources.datasources\\.yaml.apiVersion=1" \
  --set "datasources.datasources\\.yaml.datasources[0].name=Prometheus" \
  --set "datasources.datasources\\.yaml.datasources[0].type=prometheus" \
  --set "datasources.datasources\\.yaml.datasources[0].url=http://prometheus:9090" \
  --set "datasources.datasources\\.yaml.datasources[0].isDefault=true"

# Access Grafana (login: admin / <your-clickhouse-admin-password>)
kubectl port-forward -n clickstack svc/grafana 3000:80
```

---

### Backup

Deploys [clickhouse-backup](https://github.com/Altinity/clickhouse-backup) as a sidecar alongside each ClickHouse pod. Exposes a REST API on port 7171 for triggering and managing backups. Uses the `admin` user credentials automatically.

When `garage.enabled=true`, the backup sidecar reads S3 credentials directly from the `garage-backup` secret and the S3 endpoint is set automatically to `http://<release>-garage:3900` — no manual credential configuration is needed. A Kubernetes CronJob (`<release>-backup`) runs backups on the configured schedule.

| Value | Default | Description |
|---|---|---|
| `backup.enabled` | `true` | Enable the backup sidecar and CronJob |
| `backup.image.repository` | `altinity/clickhouse-backup` | Backup image |
| `backup.image.tag` | `"2.7.2"` | Image tag |
| `backup.image.pullPolicy` | `IfNotPresent` | Pull policy |
| `backup.s3.bucket` | `"clickhouse"` | S3 bucket name |
| `backup.s3.path` | `"clickhouse-backup/"` | Path prefix within the bucket |
| `backup.s3.endpoint` | `""` | S3 endpoint URL. Auto-set to Garage when `garage.enabled=true`. Leave empty for AWS S3. |
| `backup.s3.region` | `"garage"` | S3 region |
| `backup.s3.accessKey` | `""` | S3 access key. Ignored when `garage.enabled=true`. |
| `backup.s3.secretKey` | `""` | S3 secret key. Ignored when `garage.enabled=true`. |
| `backup.s3.forcePathStyle` | `true` | Required for non-AWS S3 (Garage, MinIO, etc.) |
| `backup.keepRemote` | `7` | Number of remote backups to retain |
| `backup.schedule` | `"0 2 * * *"` | CronJob schedule (daily at 2am UTC) |
| `backup.resources.limits.cpu` | `500m` | CPU limit for backup sidecar |
| `backup.resources.limits.memory` | `512Mi` | Memory limit for backup sidecar |

**Common backup commands:**
```bash
# Trigger a backup manually
kubectl exec -n <namespace> <pod> -c clickhouse-backup -- clickhouse-backup create-and-upload

# List remote backups
kubectl exec -n <namespace> <pod> -c clickhouse-backup -- clickhouse-backup list remote

# Restore a specific backup
kubectl exec -n <namespace> <pod> -c clickhouse-backup -- clickhouse-backup restore <backup-name>
```

---

### Garage (Object Storage)

Deploys [Garage](https://garagehq.deuxfleurs.fr/) as an S3-compatible object store and configures ClickHouse to use it as an S3 disk for tiered or remote storage. Garage is a lightweight (~35MB RSS) single-binary server and ships as inline templates in this chart — no Helm subchart dependency required.

| Value | Default | Description |
|---|---|---|
| `garage.enabled` | `true` | Deploy Garage and configure ClickHouse S3 disk |
| `garage.bucket` | `clickhouse` | Bucket ClickHouse reads/writes from (auto-created by setup hook) |
| `garage.storagePolicy` | `s3_main` | ClickHouse storage policy name |
| `garage.replicationFactor` | `1` | Replication factor (1 = single-node, no redundancy) |
| `garage.rpcSecret` | (default hex) | 32-byte hex string for inter-node RPC |
| `garage.adminToken` | `"garage-admin-token-change-me"` | Token for admin API (required) |
| `garage.metricsToken` | `"garage-metrics-token-change-me"` | Token for `/metrics` endpoint |
| `garage.persistence.meta.size` | `256Mi` | Metadata volume size |
| `garage.persistence.data.size` | `20Gi` | Data volume size |

The Garage S3 API is reachable in-cluster at `http://<release>-garage:3900`. A post-install hook configures the cluster layout, creates the bucket, generates an access key (Garage requires its own `GK<24-hex>` ID format, so the key is not user-specified), and writes credentials to a Secret named `garage-backup` in the release namespace. The chart's default `podTemplate.extraEnv` injects those credentials into the ClickHouse container as `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`; the storage_config.xml references them via `from_env`.

When `backup.enabled=true` and `garage.enabled=true`, the backup sidecar automatically uses Garage as the S3 backend — no additional configuration required.

---

### Tabix UI

| Value | Default | Description |
|---|---|---|
| `tabix-ui.enabled` | `true` | Deploy the [Tabix](https://github.com/tabixio/tabix) web UI for ClickHouse |

---

### Pod Template (Advanced)

Customise the ClickHouse pod spec. All fields are optional.

| Value | Default | Description |
|---|---|---|
| `podTemplate.extraEnv` | `[]` | Extra environment variables for the ClickHouse container |
| `podTemplate.extraVolumeMounts` | data PVC at `/var/lib/clickhouse` | Extra volume mounts for the ClickHouse container |
| `podTemplate.extraVolumes` | `[]` | Extra volumes for the pod |
| `podTemplate.sidecars` | busybox disk-checker | Additional sidecar containers |

The default sidecar logs disk usage of `/var/lib/clickhouse` every 60 seconds. To disable it, set `podTemplate.sidecars: []`.

---

### Service Template (Advanced)

| Value | Default | Description |
|---|---|---|
| `serviceTemplate.type` | `ClusterIP` | Kubernetes service type (`ClusterIP`, `NodePort`, `LoadBalancer`) |
| `serviceTemplate.annotations` | `{}` | Annotations for the service |

---

## Validation (`values.schema.json`)

This chart ships a `values.schema.json`. Helm validates `values.yaml` (and any
`--set` / `-f` overrides) against it automatically on `install`, `upgrade`,
`template`, and `lint`, so mistakes fail fast:

```bash
$ helm template my-ch . --set layout.shardsCount=notanumber
Error: values don't meet the specifications of the schema(s) in the following chart(s):
clickhouse-installation:
- at '/layout/shardsCount': got string, want integer
```

Objects use `additionalProperties: true`, so custom keys (extra `users`,
`settings`, `files`, `podTemplate` entries, …) are still allowed — the schema
validates the *known* structure without blocking extensions.

The schema also carries an optional `x-form` keyword on selected properties.
Helm ignores it; it tells the [ClickHouse Manager GUI](../clickhouse-manager)
which values to surface as form fields. Adding a validated property with an
`x-form` hint makes it appear in the GUI automatically — see
[clickhouse-manager/docs/SCHEMA.md](../clickhouse-manager/docs/SCHEMA.md).

## Managing installations with a GUI

[ClickHouse Manager](../clickhouse-manager) is an optional Flask + Bootstrap web
UI to create, edit, and delete installations of this chart from a browser. It
renders this chart with `helm template` and applies the result through the
Kubernetes API. It is a separate app, not part of this chart.

---

## Example Configurations

### Single-node development instance
```yaml
layout:
  shardsCount: 1
  replicasCount: 1
coordination:
  mode: none
storage:
  data:
    size: 5Gi
    storageClassName: standard
tabix-ui:
  enabled: true
podTemplate:
  sidecars: []
```

### Production HA cluster with Keeper
```yaml
layout:
  shardsCount: 2
  replicasCount: 2
coordination:
  mode: keeper
  keeper:
    replicasCount: 3
    storage:
      size: 20Gi
      storageClassName: fast-ssd
resources:
  limits:
    cpu: 4000m
    memory: 16Gi
  requests:
    cpu: 2000m
    memory: 8Gi
storage:
  data:
    size: 500Gi
    storageClassName: fast-ssd
```

### With backup to AWS S3
```yaml
backup:
  enabled: true
  s3:
    bucket: my-clickhouse-backups
    endpoint: ""        # empty = AWS S3
    region: us-east-1
    accessKey: AKIAIOSFODNN7EXAMPLE
    secretKey: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    forcePathStyle: false
  keepRemote: 14
```

### With Garage for object storage and backup
Both are enabled by default. Credentials and endpoint are wired automatically — no extra config needed:
```yaml
garage:
  enabled: true   # default

backup:
  enabled: true   # default — S3 endpoint and credentials auto-read from garage-backup secret
  keepRemote: 14  # override retention if desired
```

---

## Troubleshooting

### ClickHouse pods not starting
```bash
kubectl logs <pod> -c clickhouse -n <namespace>
kubectl describe pod <pod> -n <namespace>
```

### Keeper not healthy
```bash
kubectl get chk <release>-clickhouse-installation-keeper -n <namespace>
kubectl logs <keeper-pod> -c clickhouse-keeper -n <namespace>
```

### PVCs stuck in Pending
Check the storage class exists and has a provisioner:
```bash
kubectl get storageclass
kubectl describe pvc -n <namespace>
```

### Backup sidecar not connecting
Verify the admin secret exists and the sidecar can reach ClickHouse on localhost:9000:
```bash
kubectl exec <pod> -c clickhouse-backup -- clickhouse-backup list local
```

### Retrieve the admin password
```bash
kubectl get secret <release>-clickhouse-installation-admin -n <namespace> \
  -o jsonpath='{.data.admin}' | base64 --decode
```
