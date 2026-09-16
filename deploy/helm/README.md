# deploy/helm

Helm-based deployment for ClickHouse on Kubernetes: an operator, a chart it
manages, and an optional GUI for driving that chart.

## Directories

| Directory | What it is | Do you deploy it directly? |
|---|---|---|
| [`clickhouse-operator/`](clickhouse-operator) | The [Altinity ClickHouse Operator](https://github.com/Altinity/clickhouse-operator) Helm chart. Installs the operator (and its CRDs — `ClickHouseInstallation`, `ClickHouseInstallationTemplate`, `ClickHouseKeeperInstallation`, `ClickHouseOperatorConfiguration`) that watches for those custom resources and turns them into StatefulSets, Services, ConfigMaps, etc. **Install this first** — nothing else works without it. | Yes — once per cluster (or per watched namespace) |
| [`clickhouse-helm-chart/`](clickhouse-helm-chart) | This repo's chart for a single ClickHouse cluster. Renders a `ClickHouseInstallation` (CHI), and optionally a `ClickHouseKeeperInstallation` (CHK) for coordination, [Garage](https://garagehq.deuxfleurs.fr/) for S3-compatible object storage, a `clickhouse-backup` sidecar + CronJob, Prometheus metrics wiring, and a [CH-UI](https://github.com/caioricciuti/ch-ui) web client. One Helm release = one ClickHouse cluster. See its [README](clickhouse-helm-chart/README.md) (full value reference) and [FEATURES.md](clickhouse-helm-chart/FEATURES.md) (what the deployed database can do). | Yes — once per ClickHouse cluster you want |
| `clickhouse-helm-chart/chris/` | A vendored/reference copy of Altinity's upstream `clickhouse` chart (installed from `https://helm.altinity.com`), kept for comparison. It is **not** used by anything else in this repo. | No |
| [`clickhouse-manager/`](clickhouse-manager) | An optional Flask + Bootstrap web GUI that creates/edits/deletes `clickhouse-helm-chart` installations by rendering the chart with `helm template` and applying the result through the Kubernetes API. Lets non-CLI users provision clusters from a form instead of hand-writing `values.yaml`. See its [README](clickhouse-manager/README.md). | Optional — install if you want a GUI instead of/alongside the Helm CLI |

Dependency order: **cluster → operator → (chart directly, or the manager GUI) → database.**

## Deploy ClickHouse

### 1. Install the operator (once per cluster)

```bash
helm install clickhouse-operator ./clickhouse-operator \
  -n clickhouse-operator --create-namespace
kubectl get crd | grep clickhouse.altinity.com   # confirm CRDs installed
```

> ⚠️ **Scope the operator to a specific namespace, not cluster-wide, if you plan to use Keeper coordination.**
> When the operator watches all namespaces (`WATCH_NAMESPACES=""`), its Keeper
> controller never reconciles a `ClickHouseKeeperInstallation` into a StatefulSet,
> so clusters using `coordination.mode: keeper` come up with no coordination.
> Set the watch namespace to match where you'll install the chart:
> ```bash
> helm install clickhouse-operator ./clickhouse-operator \
>   -n clickhouse-operator --create-namespace \
>   --set operator.watchNamespaces="{clickstack}"
> ```
> See [clickhouse-helm-chart/README.md](clickhouse-helm-chart/README.md#prerequisites) for details.

### 2. Install a ClickHouse cluster

Either drive the chart directly:

```bash
cd clickhouse-helm-chart
helm install my-ch . -n clickstack --create-namespace

# retrieve the generated admin password
kubectl get secret my-ch-clickhouse-installation-admin -n clickstack \
  -o jsonpath='{.data.admin}' | base64 --decode
```

...or run the GUI and click through it instead:

```bash
cd clickhouse-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app/app.py   # http://localhost:8080
```

### 3. Use it

Connect over HTTP (`:8123`) or native TCP (`:9000`), browse it with CH-UI
(`:5521`, enabled by default), check metrics (`:9363`), or trigger a backup via
the sidecar's REST API (`:7171`). Full walkthrough in
[clickhouse-helm-chart/FEATURES.md](clickhouse-helm-chart/FEATURES.md).

## Troubleshooting

See [clickhouse-helm-chart/README.md#troubleshooting](clickhouse-helm-chart/README.md#troubleshooting)
and [clickhouse-manager/README.md#troubleshooting](clickhouse-manager/README.md#troubleshooting).
