# Garage Access Guide

Garage runs as part of the cluster and is exposed locally via k9s port-forwarding.

## Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| S3 API  | `http://127.0.0.1:3900` | S3-compatible bucket/object access |
| Admin API | `http://127.0.0.1:3903` | Cluster management, layout, keys, buckets, `/metrics` |
| RPC     | `127.0.0.1:3901` | Inter-node RPC (not normally accessed manually) |

The admin API requires a bearer token. By default the chart sets it to
`garage-admin-token-change-me` — override with `garage.adminToken`.

## Access Methods

### S3-compatible tools (AWS CLI)

```bash
# List buckets
AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> AWS_REGION=garage \
  aws --endpoint-url http://127.0.0.1:3900 s3 ls

# List objects in a bucket
AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> AWS_REGION=garage \
  aws --endpoint-url http://127.0.0.1:3900 s3 ls s3://clickhouse/

# Upload / download
AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> AWS_REGION=garage \
  aws --endpoint-url http://127.0.0.1:3900 s3 cp ./file.csv s3://clickhouse/file.csv

AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> AWS_REGION=garage \
  aws --endpoint-url http://127.0.0.1:3900 s3 cp s3://clickhouse/file.csv ./file.csv
```

Garage requires `--region garage` (set via `AWS_REGION` or the flag); the chart
configures the same region inside the Garage server.

### From inside the cluster

Run a one-off `aws-cli` pod, pulling credentials directly from the chart's
auto-created secret:

```bash
NS=clickhouse
RELEASE=ch1
SECRET=$RELEASE-clickhouse-installation-garage-backup

AK=$(kubectl get secret -n $NS $SECRET -o jsonpath='{.data.access-key-id}' | base64 -d)
SK=$(kubectl get secret -n $NS $SECRET -o jsonpath='{.data.secret-access-key}' | base64 -d)

kubectl run -n $NS garage-ls --rm -i --restart=Never --image=amazon/aws-cli \
  --env=AWS_ACCESS_KEY_ID=$AK --env=AWS_SECRET_ACCESS_KEY=$SK --env=AWS_REGION=garage \
  -- --endpoint-url http://$RELEASE-garage:3900 s3 ls s3://clickhouse/
```

### Admin API

The admin API is used by the post-install setup hook to configure the layout,
create buckets, and import keys. Direct usage is rarely needed, but useful for
debugging:

```bash
TOKEN=garage-admin-token-change-me

# Cluster status (node list, health, layout version)
curl -sH "Authorization: Bearer $TOKEN" http://127.0.0.1:3903/v1/status | jq .

# Current layout
curl -sH "Authorization: Bearer $TOKEN" http://127.0.0.1:3903/v1/layout | jq .

# List buckets
curl -sH "Authorization: Bearer $TOKEN" http://127.0.0.1:3903/v1/bucket?list | jq .

# List keys
curl -sH "Authorization: Bearer $TOKEN" http://127.0.0.1:3903/v1/key?list | jq .
```

### Metrics

```bash
curl -sH "Authorization: Bearer <metricsToken>" http://127.0.0.1:3903/metrics
```

The metrics token is `garage.metricsToken` (default `garage-metrics-token-change-me`).

## Kubernetes Context

Garage runs in the `clickhouse` namespace as a single-pod StatefulSet:

- **Pod**: `<release>-clickhouse-installation-garage-0`
- **Service (S3 + Admin)**: `<release>-garage` — ports 3900 (S3) and 3903 (admin)
- **Headless service (RPC)**: `<release>-clickhouse-installation-garage-headless` — port 3901
- **Credentials secret**: `<release>-clickhouse-installation-garage-backup`
  - Keys: `access-key-id`, `secret-access-key`

Port-forwarding is managed by k9s. If the local ports become unreachable, reopen
k9s and re-establish the port-forward against the `<release>-garage` service for
ports 3900 and 3903.
