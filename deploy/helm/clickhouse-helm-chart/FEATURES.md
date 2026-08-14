# ClickHouse Database Features

What the deployed database can **do**, and how to use each capability. This is a
task-oriented companion to the [README](README.md), which is a value-by-value
configuration reference. Everything here is delivered by installing this chart
against the [Altinity ClickHouse Operator](https://github.com/Altinity/clickhouse-operator).

Every feature below is toggled or tuned from `values.yaml`; the value that
controls it is named in each section. Placeholders used throughout:
`<release>` = your Helm release name, `<ns>` = its namespace, `<fullname>` =
`<release>-clickhouse-installation` (unless you set `fullnameOverride`).

## Contents

- [Connecting & query interfaces](#connecting--query-interfaces)
- [Query from Claude Code (MCP)](#query-from-claude-code-mcp)
- [Cluster topology: sharding & replication](#cluster-topology-sharding--replication)
- [Coordination (Keeper / ZooKeeper)](#coordination-keeper--zookeeper)
- [Distributed DDL & the `main` cluster](#distributed-ddl--the-main-cluster)
- [Storage: local volumes](#storage-local-volumes)
- [Tiered / object storage on S3 (Garage)](#tiered--object-storage-on-s3-garage)
- [Users, authentication & access control](#users-authentication--access-control)
- [Server settings, profiles & quotas](#server-settings-profiles--quotas)
- [Custom config files](#custom-config-files)
- [Monitoring & metrics](#monitoring--metrics)
- [Backup & restore](#backup--restore)
- [Tabix web UI](#tabix-web-ui)
- [Resource limits & health probes](#resource-limits--health-probes)
- [Pod & service customization](#pod--service-customization)
- [Feature matrix](#feature-matrix)

---

## Connecting & query interfaces

The operator creates Kubernetes Services in front of the ClickHouse pods. Each
server exposes the standard ClickHouse ports:

| Port | Protocol | Use |
|---|---|---|
| `8123` | HTTP | REST/HTTP queries, `/ping` health, JDBC over HTTP |
| `9000` | Native TCP | `clickhouse-client`, native drivers (fastest) |
| `9009` | Interserver HTTP | Replica-to-replica data exchange (internal) |
| `9363` | HTTP | Prometheus metrics (when `monitoring.enabled`) |
| `7171` | HTTP | Backup REST API sidecar (when `backup.enabled`) |

**Open a SQL shell inside a pod:**
```bash
kubectl exec -it -n <ns> chi-<fullname>-main-0-0-0 -c clickhouse -- \
  clickhouse-client --user admin --password "$ADMIN_PW"
```

**Port-forward the HTTP interface to your laptop:**
```bash
kubectl port-forward -n <ns> svc/clickhouse-<fullname> 8123:8123
curl 'http://localhost:8123/?query=SELECT%20version()' \
  --user "admin:$ADMIN_PW"
```

Get `ADMIN_PW`:
```bash
kubectl get secret <fullname>-admin -n <ns> \
  -o jsonpath='{.data.admin}' | base64 --decode
```

---

## Query from Claude Code (MCP)

The repo ships a **ClickHouse MCP server** integration so you can query this
database with natural language from inside a Claude Code session — "list my
databases", "show tables in testdb", "top 10 pickup neighborhoods in trips". It
talks to the same HTTP interface (port 8123) via the official `mcp-clickhouse`
package.

Run the interactive installer from the repo root; it auto-detects the endpoint
(LoadBalancer → NodePort → minikube → localhost port-forward) and pulls the
admin password from the `<release>-clickhouse-installation-admin` secret, then
merges the server into `~/.claude/settings.json`:

```bash
./setup-mcp.sh
# non-interactive:
CH_HOST=192.168.49.2 CH_PORT=30941 CH_USER=admin CH_PASSWORD=... ./setup-mcp.sh --yes
```

Tools exposed once connected: `list_databases`, `list_tables`, `run_query`.
Queries are **read-only by default**; opt into writes with
`CLICKHOUSE_ALLOW_WRITE_ACCESS=true` and destructive ops with
`CLICKHOUSE_ALLOW_DROP=true`. Full details, manual config, and env vars are in
[../../../mcp-setup.md](../../../mcp-setup.md).

---

## Cluster topology: sharding & replication

Controlled by `layout.shardsCount` and `layout.replicasCount`.

- **Sharding** (`shardsCount > 1`) splits data horizontally across shards. Use a
  `Distributed` table engine to fan queries across them.
- **Replication** (`replicasCount > 1`) keeps N copies of each shard for HA and
  read scaling. Requires a coordination service (see next section) — replicas
  synchronize through Keeper/ZooKeeper.

Total ClickHouse pods = `shardsCount × replicasCount`. Pods are named
`chi-<fullname>-main-<shard>-<replica>-0`.

**Replicated table example** (each replica keeps its own copy):
```sql
CREATE TABLE events ON CLUSTER 'main'
(
    ts    DateTime,
    user  String,
    value Float64
)
ENGINE = ReplicatedMergeTree('/clickhouse/tables/{shard}/events', '{replica}')
ORDER BY (user, ts);
```

**Distributed table over all shards:**
```sql
CREATE TABLE events_all ON CLUSTER 'main' AS events
ENGINE = Distributed('main', currentDatabase(), events, rand());
```

The macros `{shard}` and `{replica}` are populated by the operator per pod, so
the same DDL is correct on every node.

---

## Coordination (Keeper / ZooKeeper)

Replication and `ON CLUSTER` DDL need a consensus service. Set via
`coordination.mode`:

| Mode | What it deploys | When to use |
|---|---|---|
| `keeper` (default) | A `ClickHouseKeeperInstallation` (CHK) managed by the same operator | Recommended — no external dependency |
| `zookeeper` | Nothing; points ClickHouse at your existing ensemble (`coordination.zookeeper.nodes`) | You already run ZooKeeper |
| `none` | No coordination | Single node, `replicasCount: 1`, no replication |

**Keeper HA:** `coordination.keeper.replicasCount` must be **odd** for quorum.
`1` = no fault tolerance (fine for dev; the install NOTES warn about it); use
`3` in production. When `replicasCount > 1` the chart automatically adds pod
anti-affinity so Keeper pods spread across nodes.

**Check Keeper health:**
```bash
kubectl get chk <fullname>-keeper -n <ns>
```

> ⚠️ **Operator must be scoped to a namespace for `keeper` mode.** If the CHK stays
> empty (no StatefulSet, no Keeper pod) and the CHI logs `keeper not ready ... wait
> timeout`, the operator is running cluster-wide. Its Keeper controller only
> reconciles the CHK when the operator watches a specific namespace
> (`WATCH_NAMESPACES=<ns>`), not `NamespaceAll`. See the operator note in
> [README.md](README.md#prerequisites). ClickHouse itself will still start, but
> without coordination.

---

## Distributed DDL & the `main` cluster

The chart defines a single logical cluster named **`main`** (see
`clusters:` in the rendered CHI). Reference it in `ON CLUSTER 'main'` statements
so DDL executes on every shard/replica at once. Verify the cluster topology the
server sees:
```sql
SELECT shard_num, replica_num, host_name FROM system.clusters WHERE cluster = 'main';
```

---

## Storage: local volumes

Each ClickHouse pod gets a data PVC (`storage.data`) mounted at
`/var/lib/clickhouse`. Optionally a separate log PVC (`storage.log.enabled`)
isolates ClickHouse's log tables/files from data.

| Value | Purpose |
|---|---|
| `storage.data.size` / `.storageClassName` / `.accessModes` | Primary data volume |
| `storage.log.*` | Optional dedicated log volume |

Volumes are provisioned via `volumeClaimTemplates`, so each replica gets its own
independent PVC. Leaving `storageClassName` blank uses the cluster default
StorageClass. Keeper has its own volume (`coordination.keeper.storage`).

Inspect usage (a default busybox sidecar also logs `du` every 60s):
```bash
kubectl exec -n <ns> chi-<fullname>-main-0-0-0 -c clickhouse -- df -h /var/lib/clickhouse
```

---

## Tiered / object storage on S3 (Garage)

With `garage.enabled=true` (default), the chart deploys **Garage** — a
lightweight (~35 MB RSS) single-binary S3-compatible object store — and wires
ClickHouse to use it as an **S3 disk**. This lets you keep hot data on local
disk and offload cold data to cheap object storage using a storage policy.

What the chart sets up automatically:

- A Garage server reachable in-cluster at `http://<release>-garage:3900` (S3
  API) and `:3903` (admin API).
- A post-install hook that configures the cluster layout, creates the bucket
  (`garage.bucket`), generates an access key (Garage requires its own
  `GK<24-hex>` key format), and stores credentials in the `garage-backup` Secret.
- A `storage_config.xml` defining an `s3_disk` and a storage policy named
  `garage.storagePolicy` (default `s3_main`). Credentials are injected into the
  ClickHouse container via `from_env` so no secret ever lands in the config.

**Put a table (or part of one) on S3** by selecting the policy:
```sql
CREATE TABLE cold_events
(
    ts DateTime,
    payload String
)
ENGINE = MergeTree
ORDER BY ts
SETTINGS storage_policy = 's3_main';
```

Or add a TTL move to tier data automatically:
```sql
ALTER TABLE events MODIFY TTL ts + INTERVAL 30 DAY TO VOLUME 'main';
```

Set `garage.enabled=false` to use an external S3 (AWS, MinIO, …) instead — see
the backup section and the README's Garage table. **Change the default
`rpcSecret`, `adminToken`, and `metricsToken` before any real use.**

---

## Users, authentication & access control

Users are declared under `users` and rendered into the CHI's `users` config.

- **`default` user** — `users.default.password`, `users.default.networks/ip`
  (`0.0.0.0/0` = connect from anywhere; tighten for real deployments).
- **`admin` user** — full `access_management: '1'`, so you can `CREATE USER` /
  `GRANT` at runtime. Its password is auto-generated (or set `adminPassword`)
  and stored in the `<fullname>-admin` Secret. On `helm upgrade` the existing
  secret is preserved via `lookup`, so the password does not rotate unexpectedly.
- **Additional users** — add any key under `users` with `password`, `profile`,
  `networks/ip`, etc.

```yaml
users:
  analyst:
    password: "s3cr3t"
    profile: readonly
    networks/ip: "10.0.0.0/8"
```

Because `admin` has access management, you can also manage users in SQL:
```sql
CREATE USER reporting IDENTIFIED BY 'pw';
GRANT SELECT ON analytics.* TO reporting;
```

---

## Server settings, profiles & quotas

Three value maps flow straight into ClickHouse config using dot-path keys:

| Value | Maps to | Example |
|---|---|---|
| `settings` | server `config.xml` | `max_connections: "500"`, `compression/case/method: zstd` |
| `profiles` | user profiles (`users.xml`) | `readonly/readonly: "1"`, `default/max_memory_usage: 10000000000` |
| `quotas` | query quotas | `default/interval/queries: "1000"` |

Profiles are per-session limits you attach to users; quotas cap resource usage
over a time interval. Both are empty by default. Verify what the server loaded:
```sql
SELECT name, value FROM system.settings WHERE changed;
SELECT * FROM system.quotas;
```

---

## Custom config files

`files` mounts arbitrary XML into ClickHouse's config directory — dictionaries,
custom disks, named collections, etc.:
```yaml
files:
  dict_source.xml: |
    <clickhouse>
      <dictionary>...</dictionary>
    </clickhouse>
```
The chart already synthesizes `prometheus.xml` (monitoring) and
`storage_config.xml` (Garage) this way; your `files` entries are merged alongside.

---

## Monitoring & metrics

With `monitoring.enabled=true` (default), ClickHouse exposes a Prometheus
endpoint on `monitoring.prometheus.port` (9363) at `/metrics`, and the pods get
`prometheus.io/scrape`, `/port`, `/path` annotations so a standard Prometheus
auto-discovers them. Set `monitoring.serviceMonitor=true` if you run the
Prometheus Operator and prefer a `ServiceMonitor`.

```bash
kubectl port-forward -n <ns> chi-<fullname>-main-0-0-0 9363:9363
curl -s localhost:9363/metrics | head
```

Rich internal telemetry is always available in SQL regardless of this setting:
```sql
SELECT * FROM system.metrics;
SELECT * FROM system.asynchronous_metrics;
SELECT * FROM system.events;
```
The README has a copy-paste Prometheus + Grafana install (Grafana logs in with
the ClickHouse admin password).

---

## Backup & restore

With `backup.enabled=true` (default) each ClickHouse pod runs an
[clickhouse-backup](https://github.com/Altinity/clickhouse-backup) sidecar
exposing a REST API on port 7171, plus a Kubernetes CronJob (`<fullname>-backup`)
that runs on `backup.schedule` (default daily 02:00 UTC) and retains
`backup.keepRemote` remote backups.

- **With Garage** (`garage.enabled=true`): the S3 endpoint and credentials are
  wired automatically from the `garage-backup` secret — zero backup config.
- **With external S3**: set `backup.s3.endpoint/region/accessKey/secretKey` and
  `forcePathStyle` (`false` for AWS, `true` for MinIO/others).

```bash
# create + upload now
kubectl exec -n <ns> <pod> -c clickhouse-backup -- clickhouse-backup create-and-upload
# list what's stored remotely
kubectl exec -n <ns> <pod> -c clickhouse-backup -- clickhouse-backup list remote
# restore
kubectl exec -n <ns> <pod> -c clickhouse-backup -- clickhouse-backup restore <backup-name>
```
Backups use the `admin` credentials automatically. The sidecar also creates
integration tables so you can drive backups from SQL (`system.backup_actions`).

---

## Tabix web UI

`tabix-ui.enabled=true` (default) deploys the [Tabix](https://github.com/tabixio/tabix)
browser SQL client:
```bash
kubectl port-forward -n <ns> svc/<release>-tabix-ui 8080:80
# open http://localhost:8080, connect to the ClickHouse HTTP endpoint
```

---

## Resource limits & health probes

- `resources` sets CPU/memory requests & limits on the ClickHouse container
  (`backup.resources` and `coordination.keeper.resources` for those containers).
- `livenessProbe` / `readinessProbe` hit `GET /ping` on 8123; tune the initial
  delay and periods per environment. Keeper uses TCP probes on 2181.

---

## Pod & service customization

For anything the structured values don't cover, `podTemplate` and
`serviceTemplate` pass through to the operator's pod/service spec:

| Value | Effect |
|---|---|
| `podTemplate.extraEnv` | Extra env vars (used by default to inject Garage S3 creds) |
| `podTemplate.extraVolumeMounts` / `extraVolumes` | Mount extra storage into ClickHouse |
| `podTemplate.sidecars` | Add sidecar containers (a busybox disk-usage logger ships by default; `[]` to remove) |
| `serviceTemplate.type` | `ClusterIP` / `NodePort` / `LoadBalancer` for external exposure |
| `serviceTemplate.annotations` | Service annotations (e.g. cloud LB config) |

Set `serviceTemplate.type: LoadBalancer` to expose ClickHouse outside the
cluster (secure it first — the `default` user allows all source IPs by default).

---

## Feature matrix

| Feature | Value(s) | Default |
|---|---|---|
| Sharding | `layout.shardsCount` | 1 (off) |
| Replication | `layout.replicasCount` + coordination | 2 replicas |
| Keeper coordination | `coordination.mode: keeper` | on |
| S3 tiered storage (Garage) | `garage.enabled` | on |
| Scheduled backups | `backup.enabled` | on |
| Prometheus metrics | `monitoring.enabled` | on |
| Tabix UI | `tabix-ui.enabled` | on |
| Claude Code MCP querying | `setup-mcp.sh` (repo root) | opt-in |
| Separate log volume | `storage.log.enabled` | off |
| Admin access management | `users.admin.access_management` | on |

See the [README](README.md) for the full value reference and the
[ClickHouse Manager GUI](../clickhouse-manager) to drive all of this from a
browser.
