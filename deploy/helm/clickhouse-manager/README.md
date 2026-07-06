# ClickHouse Manager

A small **Flask + Bootstrap** web GUI to create and manage ClickHouse clusters.
Each "installation" is a full `ClickHouseInstallation` (CHI) rendered from the
sibling [`clickhouse-helm-chart`](../clickhouse-helm-chart) and applied through
the Kubernetes API.

The GUI form is generated from the chart's `values.schema.json`, so the file
Helm uses to *validate* values is the same file that *drives the form* — see
[docs/SCHEMA.md](docs/SCHEMA.md).

## Contents

- [Quick start](#quick-start)
- [Prerequisites](#prerequisites)
- [What it does](#what-it-does)
- [Why a separate app](#why-a-separate-app)
- [Architecture](#architecture)
- [File map](#file-map)
- [Data model](#data-model)
- [Request lifecycle](#request-lifecycle)
- [Configuration](#configuration)
- [HTTP endpoints](#http-endpoints)
- [Run locally](#run-locally)
- [Build the image](#build-the-image)
- [Deploy to a cluster](#deploy-to-a-cluster)
- [Schema-driven form](#schema-driven-form)
- [Validation](#validation)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Limits & roadmap](#limits--roadmap)

## Quick start

Starting from nothing. The GUI **creates** ClickHouse databases, so you do
**not** need one running first — but you do need a Kubernetes cluster and the
ClickHouse Operator. Dependency chain: **cluster → operator → GUI → (click
Create) → database.**

Run these from the repository root.

**1. A Kubernetes cluster** (skip if you already have one). Use either kind or
minikube:

```bash
# Option A — kind
kind create cluster --name ch

# Option B — minikube (enable the default StorageClass + provisioner addons)
minikube start -p ch
minikube -p ch addons enable default-storageclass
minikube -p ch addons enable storage-provisioner

kubectl cluster-info                       # confirm your context works
```

`minikube start` also switches your kubectl context to the new cluster. To point
back at it later: `kubectl config use-context ch`.

```bash
# 2. Install the ClickHouse Operator (adds the CHI/CHK CRDs the GUI creates).
#    CRDs install automatically via the chart's hooks; it watches all namespaces.
helm install clickhouse-operator ./deploy/helm/clickhouse-operator \
  -n clickhouse --create-namespace
kubectl get crd | grep clickhouse.altinity.com     # verify CRDs exist

# 3. Start the GUI locally (CHART_PATH defaults to ../clickhouse-helm-chart).
cd deploy/helm/clickhouse-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app/app.py                          # http://localhost:8080
```

Open **http://localhost:8080**. The home page loads empty ("No managed
installations yet") — that's expected, no database exists yet.

Click **+ New Installation**, fill the form, and **Create installation**. Then:

```bash
kubectl get chi -A            # your new ClickHouseInstallation
kubectl get pods -n default   # clickhouse + keeper pods starting
```

> **kind / minikube tip:** leave the **Storage class** field blank. Blank uses
> the cluster's default StorageClass (`standard` on both kind and minikube)
> instead of the chart's `hostpath` default, which may not exist on your cluster.
> Confirm with `kubectl get storageclass` — the default is marked `(default)`.

To run the GUI *in the cluster* instead of locally, see
[Deploy to a cluster](#deploy-to-a-cluster).

## Prerequisites

| Requirement | Needed to start the GUI? | Needed to create a database? |
|---|---|---|
| Kubernetes cluster + valid kubeconfig | ✅ yes — the K8s client initializes at startup | ✅ |
| ClickHouse Operator (CHI/CHK CRDs) | ❌ no | ✅ yes — reconciles the CHI into pods |
| A running ClickHouse database | ❌ no | — the GUI creates one |
| `helm` + Python 3.9+ (local run) | ✅ | ✅ |

If you start the GUI with no reachable cluster, the process fails on boot (the
Kubernetes client is initialized at import) rather than showing a friendly
error.

## What it does

1. **Lists** managed installations (home page) with live CHI status.
2. **Creates / edits** an installation from a form whose fields come from the
   chart's `values.schema.json`, plus an *Advanced values (YAML)* box for
   anything not surfaced as a field.
3. **Renders** the chart with `helm template` — the chart stays the single
   source of truth for how values become a CHI (and its Keeper, Secrets,
   ConfigMaps, backup CronJob, Garage, etc.).
4. **Applies** the rendered manifests through the **Kubernetes API**
   (create-or-patch), *not* `helm install` — no Tiller/release state to manage.
5. **Validates** submitted values against `values.schema.json` before applying,
   exactly as Helm would.
6. **Deletes** an installation by re-rendering and removing its manifests.

## Why a separate app

The `clickhouse-installation` chart *is one database cluster*. A control panel
that manages *many* clusters can't live inside a single instance of the thing it
manages, and it needs cluster-level RBAC you would not want attached to every
data pod. So this ships as its own image + manifests and leaves the chart
untouched.

## Architecture

```
Browser ──► Flask (app.py)
               │  build_values(form)  ────────────────► chart.py
               │     schema fields + Advanced YAML
               │  validate(values) vs values.schema.json ─► schema.py
               │  helm template <chart> ──────────────► manifests[]
               │  K8s API create/patch ───────────────► CHI, CHK, Secrets,   k8s.py
               │                                          ConfigMaps, CronJob…
               │  save values ─────────────────────────► ConfigMap chmanager-<name>
               ▼
          ClickHouse Operator reconciles the CHI ──► pods / services / PVCs
```

## File map

| File | Responsibility |
|---|---|
| `app/app.py` | Flask routes, request handling, flash messaging |
| `app/schema.py` | Loads `values.schema.json`, builds the form model, path helpers, validation |
| `app/chart.py` | `build_values()` (form → values) and `helm template` rendering |
| `app/k8s.py` | Kubernetes access: apply/patch/delete manifests, ConfigMap-backed inventory, CHI status |
| `app/templates/` | Bootstrap 5 pages: `index`, `form`, `detail`, `base` |
| `deploy/rbac.yaml` | ServiceAccount + ClusterRole/Binding |
| `deploy/deployment.yaml` | Namespace, Deployment, Secret, Service |
| `Dockerfile` | Python image with `helm` and the chart baked in |
| `docs/SCHEMA.md` | How the schema drives the form (full reference) |

## Data model

The manager is **stateless** apart from one `ConfigMap` per installation — that
is the source of truth for what it manages:

| | |
|---|---|
| Name | `chmanager-<release>` |
| Namespace | the installation's namespace |
| Label | `app.kubernetes.io/managed-by=clickhouse-manager` |
| Data | `release` (name) and `values.yaml` (the submitted values subset) |

The home page lists installations by querying these ConfigMaps cluster-wide;
each row is enriched with live status from the corresponding CHI. Edits reload
the stored values into the form; deletes re-render from them so every resource
the chart created is removed.

## Request lifecycle

**Create / edit** (`POST /apply`):
`build_values(form)` → `validate()` against the schema → `helm template` →
`k8s.apply_manifests()` (create or merge-patch each doc; Jobs are recreated
since they're immutable) → save the `chmanager-<release>` ConfigMap.

**Delete** (`POST /delete/...`): load stored values → `helm template` →
`k8s.delete_manifests()` (reverse order) → delete the ConfigMap.

Helm *test* hooks (connectivity-test pods) are filtered out during rendering so
they're never deployed as permanent resources.

## Configuration

Environment variables (see `deploy/deployment.yaml`):

| Variable | Default | Purpose |
|---|---|---|
| `CHART_PATH` | `../clickhouse-helm-chart` (local) / `/chart` (image) | Path to the chart to render |
| `SCHEMA_JSON` | `$CHART_PATH/values.schema.json` | Schema that drives the form and validation |
| `DEFAULT_NAMESPACE` | `default` | Pre-filled namespace on the New form |
| `SECRET_KEY` | `change-me-in-production` | Flask session/flash signing key |
| `PORT` | `8080` | Port the app listens on (local `app.py`) |

## HTTP endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | List installations + schema-issue banner |
| GET | `/new` | Create form |
| GET | `/edit/<ns>/<release>` | Edit form (prefilled) |
| POST | `/apply` | Validate, render, apply, save |
| GET | `/detail/<ns>/<release>` | Status + rendered manifests |
| POST | `/delete/<ns>/<release>` | Delete installation |
| GET | `/healthz` | Liveness/readiness probe |

## Run locally

The fastest way to try it — see [Quick start](#quick-start) for the full
from-scratch flow (cluster + operator). Requires a working `~/.kube/config`,
`helm`, and Python 3.9+.

```bash
cd deploy/helm/clickhouse-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# CHART_PATH defaults to ../clickhouse-helm-chart
python app/app.py            # http://localhost:8080
```

## Build the image

Build from the `deploy/helm` directory so both the chart and the app are in the
build context (the chart is baked in so `helm template` works offline):

```bash
cd deploy/helm
docker build -f clickhouse-manager/Dockerfile -t clickhouse-manager:dev .
```

## Deploy to a cluster

Runs the GUI as a pod using the in-cluster ServiceAccount (from `rbac.yaml`)
instead of your kubeconfig. The operator must already be installed (see
[Quick start](#quick-start) step 2). After [building the image](#build-the-image):

```bash
# Load the local image into the cluster first:
kind load docker-image clickhouse-manager:dev --name ch       # kind
minikube -p ch image load clickhouse-manager:dev              # minikube

kubectl apply -f clickhouse-manager/deploy/rbac.yaml
kubectl apply -f clickhouse-manager/deploy/deployment.yaml   # edit image + secret first
kubectl -n clickhouse-manager port-forward svc/clickhouse-manager 8080:80
# open http://localhost:8080
```

The `ClusterRole` in `rbac.yaml` grants the verbs the manager needs on CHIs,
CHKs, and the resources the chart renders (ConfigMaps, Secrets, Services, PVCs,
Jobs, CronJobs, ServiceMonitors). Scope it to specific namespaces with a
`Role`/`RoleBinding` if you don't need cluster-wide management.

## Schema-driven form

The form is generated from the chart's **`values.schema.json`** — the same file
Helm uses to validate `values.yaml`. Add a property (with an `x-form` hint) to
that file and it appears in the GUI automatically, with no Python or template
changes. Full reference, keyword mapping, and worked examples:
**[docs/SCHEMA.md](docs/SCHEMA.md)**.

Anything not annotated is still editable per-install via the **Advanced values
(YAML)** box, deep-merged into the values (structured fields win on overlapping
paths).

## Validation

Submitted values are checked against `values.schema.json` before applying and
errors are shown in the UI — the same failures Helm would raise. The home page
also flags a missing or invalid schema. Run the same check from the CLI (wire it
into CI):

```bash
python app/schema.py        # validates values.yaml; prints field/group summary
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Home page: "Could not reach the cluster" | No/invalid kubeconfig, or the pod's ServiceAccount lacks RBAC. Check `deploy/rbac.yaml` is applied. |
| "Schema issues" banner | `values.schema.json` missing at `SCHEMA_JSON`, or `values.yaml` violates it. Run `python app/schema.py`. |
| "Validation failed: …" on apply | The submitted value violates the schema (e.g. a non-integer shard count). Fix the field and resubmit. |
| "Failed to create …: … helm template" | Chart render error; the message is helm's stderr. Reproduce with `helm template <name> ../clickhouse-helm-chart -f <values>`. |
| Installation missing from the list | Its `chmanager-<release>` ConfigMap was deleted, or you're filtering the wrong namespace. The CHI may still exist. |
| Job "field is immutable" on edit | Expected — hook Jobs are deleted and recreated on apply. |

## Security

- **No authentication.** Keep it behind `port-forward` or an authenticated
  ingress. Do not expose it publicly as-is.
- The ServiceAccount is **cluster-privileged** over the resources listed in
  `rbac.yaml`. Anyone who can reach the app can create/delete ClickHouse
  clusters. Restrict network access and scope RBAC down where possible.
- Passwords entered in the form are written into chart-generated Secrets and
  into the `chmanager-<release>` ConfigMap (values). Treat that ConfigMap as
  sensitive or move secret values to the Advanced box / external secrets.
- Set a real `SECRET_KEY`.

## Limits & roadmap

- **Scope = provisioning clusters.** Managing databases/tables *inside* a
  running cluster (SQL `CREATE DATABASE`) is out of scope; add it later by
  talking to ClickHouse HTTP `:8123`.
- Helm hook Jobs (e.g. the Garage setup hook) are applied as normal resources
  and recreated on each apply.
- `users` is a free-form map in the chart; only `users.default.password` is a
  friendly field. Manage additional users via the Advanced YAML box.
