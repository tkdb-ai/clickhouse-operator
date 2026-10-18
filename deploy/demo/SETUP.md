# Demo setup

What to do on the presenting laptop, in order. Run every command from
`deploy/demo/` unless a step says otherwise. Steps 1 and 2 are once per minikube
cluster; after a `make down`, start again at step 1.

`make setup` runs steps 1 to 4 in one go. The steps below are the same thing,
one at a time, with what to check after each.

## 0. Tools

Docker with 9+ GiB of memory (3 nodes x `MINIKUBE_MEMORY`, default 3g), minikube
1.34+, kubectl, helm (3.14+ or 4.x) and Python 3.10+.

```bash
make prereqs
python3 -m pip install -r requirements-dev.txt   # for make test
```

## 1. Cluster

```bash
scripts/01-cluster-up.sh
```

This starts the minikube profile `ch-demo` with 3 nodes, makes rancher's
local-path-provisioner the default StorageClass, puts one zone label on each
node (zone-a/b/c), and preloads the ClickHouse and Keeper images.

Check: `kubectl get nodes -L topology.kubernetes.io/zone` shows three nodes in
three zones, and `kubectl get sc` shows `local-path (default)`.

## 2. Operator (once per cluster)

The demo treats the Altinity operator as platform: installed once, on its own,
before any database. Install it from this repo's chart
(`deploy/helm/clickhouse-operator`, 0.27.3), watching only `ch-demo`:

```bash
make operator
# which runs:
helm upgrade --install clickhouse-operator ../helm/clickhouse-operator \
  -n clickhouse-operator --create-namespace \
  --set 'watchNamespaces={ch-demo}' --wait
```

`watchNamespaces` is a top-level value of the operator chart. It must include
`ch-demo`. This repo's copy of the chart defaults to `[clickhouse, demo1, demo2]`,
which does not include `ch-demo`, so always pass it as above (`make operator`
does). Left empty, the operator watches only its own namespace; installed in
kube-system it watches everything, and then the Keeper never comes up (see
`deploy/helm/clickhouse-helm-chart/README.md`, Prerequisites).

Optionally preload its images too, so a later restart never pulls on venue Wi-Fi:

```bash
minikube image load altinity/clickhouse-operator:0.27.3 -p ch-demo
minikube image load altinity/metrics-exporter:0.27.3 -p ch-demo
```

Check:

```bash
kubectl get crd | grep altinity          # clickhouseinstallations and clickhousekeeperinstallations
kubectl -n clickhouse-operator get pods  # operator pod Running, 2/2
```

If you installed the operator some other way, set `OPERATOR_NS` (and
`OPERATOR_RELEASE` for the monitoring step) to where it lives.

## 3. Database

```bash
scripts/02-helm-install.sh
```

The script first checks the operator: both CRDs exist, an operator pod is Ready,
and it prints the operator's watch config. Then one `helm install` of
`../helm/clickhouse-helm-chart` with `helm/values.yaml` creates a 3-node Keeper
and 2 shards x 2 replicas. If no Keeper pods appear within 3 minutes it stops
and tells you to check `watchNamespaces` instead of hanging.

Check: `kubectl -n ch-demo get chi,chk,pods -o wide` shows CHI `demo`
Completed, CHK `demo-keeper`, three Keeper pods and four `chi-demo-main-*` pods,
with the two replicas of each shard on different nodes.

## 4. Data

```bash
scripts/03-load-data.sh   # schema ON CLUSTER main, then ~3M NYC taxi trips from S3
make queries              # sanity check
make test && make test-live
```

## 5. MCP server: query the demo from Claude Code (optional)

This uses the repo's [`setup-mcp.sh`](../../setup-mcp.sh) and
[`mcp-setup.md`](../../mcp-setup.md). You need `jq`, `curl` and a way to launch
`mcp-clickhouse`; `uv` is easiest (`brew install uv`, then the script uses
`uvx mcp-clickhouse`).

Three things differ from the script's defaults for this demo.

**Connect through a port-forward.** The `clickhouse-demo` Service is ClusterIP,
and with minikube's Docker driver on macOS the node IP isn't reachable from the
Mac anyway. Keep a port-forward running in its own terminal for the whole talk.
A port-forward attaches to one pod and drops when that pod restarts (the chaos
and rolling-upgrade steps), so wrap it in a loop:

```bash
while true; do kubectl -n ch-demo port-forward svc/clickhouse-demo 8123:8123; sleep 1; done
```

**Pass the credentials.** The script looks for a secret named
`<HELM_RELEASE>-clickhouse-installation-admin` (default `ch1`). With
`fullnameOverride: demo` the secret is `demo-admin`, so auto-detection finds
nothing. The `demo` user is simplest, and the MCP server stays read-only:

```bash
curl -fsS -u demo:demo http://localhost:8123/ping   # expect "Ok."
cd ../..                                            # repo root
CH_HOST=localhost CH_PORT=8123 CH_USER=demo CH_PASSWORD=demo CH_ALLOW_WRITE=false ./setup-mcp.sh --yes
```

For `admin` instead: `kubectl -n ch-demo get secret demo-admin -o jsonpath='{.data.admin}' | base64 -d`.

**Check Claude Code picked it up.** The script writes `mcpServers` into
`~/.claude/settings.json`. Restart Claude Code and run `claude mcp list` (or
`/mcp` in a session). If `clickhouse` isn't listed, register it with the CLI:

```bash
claude mcp add clickhouse --scope user \
  -e CLICKHOUSE_HOST=localhost -e CLICKHOUSE_PORT=8123 \
  -e CLICKHOUSE_USER=demo -e CLICKHOUSE_PASSWORD=demo -e CLICKHOUSE_SECURE=false \
  -- uvx mcp-clickhouse
```

Try "list my ClickHouse databases" (you should see `demo`), then "top 10 pickup
neighborhoods in demo.trips". Queries go through the Distributed table, so the
answer covers every shard.

## 6. Between rehearsals

`make reset` puts the release back to `helm/values.yaml` (2x2 on 24.8) and
reloads the data. `make down` deletes the whole minikube profile, operator
included.
