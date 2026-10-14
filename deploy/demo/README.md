# ClickHouse on Kubernetes: demo kit

A laptop-sized, reproducible demo of a sharded, replicated ClickHouse cluster on
a local 3-node `minikube` cluster, deployed with this repo's chart
[`deploy/helm/clickhouse-helm-chart`](../helm/clickhouse-helm-chart) on top of the
Altinity operator from [`deploy/helm/clickhouse-operator`](../helm/clickhouse-operator)
(0.27.3), which is installed once, on its own.
The whole database is one file, [`helm/values.yaml`](helm/values.yaml). Every
step on stage is a `helm upgrade` that changes one value; Helm records it as a
numbered release, and the operator reconciles the cluster to match.

| Step | Script | What the audience sees |
|---|---|---|
| 1 | `01-cluster-up.sh` | 3-node minikube cluster, each node labelled as its own zone, local-path storage |
| - | `install-operator.sh` | Once per cluster, before the talk: the operator as its own release, watching `ch-demo` |
| 2 | `02-helm-install.sh` | One `helm install -f helm/values.yaml`: 3-node Keeper, 2 shards x 2 replicas |
| 3 | `03-load-data.sh` | ~3M real NYC taxi trips loaded straight from S3 through a Distributed table |
| 4 | `04-scale.sh shards 3` | `--set layout.shardsCount=3`: new shard, schema copied, ~2M more trips land there too |
| 4b | `04-scale.sh replicas 3` | `--set layout.replicasCount=3`: new replicas fetch data from peers via Keeper |
| 5 | `05-live-config.sh` | `--set-string profiles.default/max_memory_usage=...`: zero pod restarts |
| 6 | `06-rollback.sh` | `helm rollback`: the previous release comes back, still no restarts |
| 7 | `07-rolling-upgrade.sh` | `--set-string image.tag=25.3`: one host at a time, queries keep working |
| 8 | `08-chaos.sh` | Delete a pod; it comes back with the same PVC and data |
| - | `watch-availability.sh` | Second terminal: a query every second, OK/FAIL |
| - | `render.sh` | `helm template`: the CHI/CHK the chart hands the operator |

Each step uses `helm upgrade --reuse-values --set ...`, so changes stack on the
last release and `helm history demo -n ch-demo` lists them all. `make reset`
re-applies `helm/values.yaml` without `--reuse-values`, discarding them.

See [SETUP.md](SETUP.md) for the setup steps (cluster, operator, database, data, MCP server) and [RUNSHEET.md](RUNSHEET.md) for the minute-by-minute stage script.

## Requirements

Docker with about 10 GB of memory (minikube uses `MINIKUBE_MEMORY`, default 3g, per node, x 3 nodes), `minikube` 1.34+, `kubectl`,
`helm` 3.14+, Python 3.10+. Internet access for setup (images) and
for the taxi data, which ClickHouse reads from the public ClickHouse docs bucket
(`datasets-documentation.s3.eu-west-3.amazonaws.com/nyc-taxi/`, about 82 MB per
million trips).

```bash
make prereqs
make setup          # cluster, operator, database, data: about 5-8 minutes on first run
TAXI_FILES=0..19 scripts/03-load-data.sh   # optional: all 20M trips (~1.6 GB download)
make test           # offline tests
make test-live      # smoke tests against the running cluster
```

## minikube settings

`make setup` creates (or reuses) the minikube profile `ch-demo`. Override with
`MINIKUBE_MEMORY` (per node, default `3g`), `MINIKUBE_CPUS` (default 2),
`MINIKUBE_NODES` (default 3; Keeper needs 3 nodes, one per zone),
`MINIKUBE_DRIVER` (default: minikube's choice) and `K8S_VERSION` (default
`v1.31.0`). `make down` runs `minikube delete -p ch-demo`.

## Using your own values.yaml

Point the scripts at it: `VALUES=/path/to/values.yaml make setup` (and
`RELEASE=...` if your release isn't called `demo`). The scripts assume
`fullnameOverride` equals the release name, so the CHI is `demo` and the CHK
`demo-keeper`; the chart always calls the ClickHouse cluster `main`. They also
assume `users` has a `demo` user with password `demo`. Run `make test` afterwards: it renders your file with the chart
and fails on anything the demo steps rely on.

## Layout

```
helm/values.yaml        the whole database: Keeper, 2x2 layout, users, profiles, disks
manifests/client.yaml   long-lived client pod that queries through the Service
sql/                    NYC taxi schema (ReplicatedMergeTree + Distributed), S3 loader, queries
scripts/                one script per demo step, plus reset/teardown/monitoring
tests/                  pytest: values vs chart + CRDs, SQL via chdb on a 1,000-trip sample, live smoke tests
```

## Tests

* `tests/test_helm.py` validates `helm/values.yaml` against the chart's own
  `values.schema.json`, renders it with `helm template`, and validates the
  resulting CHI and CHK against the operator's CRD schemas
  (`deploy/helm/clickhouse-operator/crds`). It checks Keeper quorum size, zone
  spreading and anti-affinity that fits 3 nodes, pinned images, that the
  chart's add-ons (operator subchart, Garage, backup, CH-UI, cron sidecar) are
  off, that ClickHouse points at the Keeper, that numbers don't render as `1e+09` (Helm does that to
  unquoted big integers), that every `--set` key used by the scripts exists
  (Helm silently ignores a misspelt one), and that each step's `--set` really
  changes what it should. Rendering tests skip if `helm` isn't on the PATH.
* `tests/test_sql.py` parses every SQL statement, then runs the real loader
  (pointed at `tests/fixtures/trips_sample.tsv`, 1,000 trips from `trips_1.gz`)
  and every analytic query on embedded ClickHouse (`chdb`). Skipped if chdb
  isn't installed.
* `tests/test_cluster.py` (`make test-live`) checks the live cluster: CHI
  owned by the Helm release and matching `helm get values`, reconciled, one Ready pod per host, ClickHouse topology equals the CHI spec,
  Keeper reachable, replicas of each shard agree, Distributed total equals the
  sum of shards, no read-only or lagging replicas, and an insert round-trip.
  Assertions read the current CHI, so rerun it after each step.

## Notes and honest caveats

* Credentials (`demo/demo`) are demo-only, stored as `password_sha256_hex`.
  Use `password_secret_name` in real deployments.
* The operator is its own release (`operator.enabled: false` here), as in
  production. A chart that bundles it would remove the operator first on
  `helm uninstall`, and the CHI finalizers would hang.
* The chart's default anti-affinity (one ClickHouse pod per node across the whole
  installation) can't place 2x2 on 3 nodes, so `helm/values.yaml` scopes it to a
  shard, and spreads pods across zones with `topologySpreadConstraints` on the
  operator's `clickhouse.altinity.com/chi` label.
* The chart turns on Garage, clickhouse-backup, CH-UI and a cron sidecar by
  default. The demo turns them off: the sidecar's image is built locally and
  isn't in any registry, and the rest add pods and image pulls that don't help
  the story on stage.
* minikube's built-in `standard` StorageClass doesn't pin volumes to a node,
  so on a multi-node cluster a pod that moves can come back to an empty disk.
  `01-cluster-up.sh` installs rancher's local-path-provisioner and makes it the
  default instead: each volume is bound to its node, like a real local SSD, which
  is why a deleted pod comes back on the same node with its data. Still no
  volume expansion and no cross-node moves. On EKS/GKE/AKS use an expandable CSI class
  (gp3, pd-ssd, Premium SSD v2) and the PVC resize becomes a live demo too.
* The source files label card and cash payments backwards (the cash rows carry
  the tips, which TLC only records for cards), so `sql/load.sql` swaps them back.
* Adding a shard does not move existing data. Rebalance with
  `INSERT INTO ... SELECT`, shard weights, or a new table + swap.
* Verified offline only: `helm template` with the in-repo chart, CHI/CHK against the CRD schemas, SQL on ClickHouse
  26.9 via chdb, shell scripts with shellcheck. Do one full rehearsal on the
  presenting laptop.
