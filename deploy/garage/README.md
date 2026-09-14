# garage

![Version: 0.10.2](https://img.shields.io/badge/Version-0.10.2-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: v2.4.1](https://img.shields.io/badge/AppVersion-v2.4.1-informational?style=flat-square)

S3-compatible object store for small self-hosted geo-distributed deployments

**Homepage:** <https://garagehq.deuxfleurs.fr/>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| Garage maintainer team | <garagehq@deuxfleurs.fr> |  |

## Source Code

* <https://git.deuxfleurs.fr/Deuxfleurs/garage.git>

## CLI Usage

### Installing the garage client

Download the `garage` binary matching the chart's app version:

```bash
curl -Lo garage https://garagehq.deuxfleurs.fr/download/v2.4.1/x86_64-unknown-linux-musl/garage
chmod +x garage
sudo mv garage /usr/local/bin/
```

### Connecting to a running instance

The garage CLI connects over RPC (port 3901). You need the full node ID and the RPC secret.

**1. Port-forward the RPC port** (in a separate terminal):

```bash
kubectl port-forward -n <namespace> <pod-name> 3901:3901
```

**2. Get the full node ID** from the GarageNode CRD:

```bash
kubectl get garagenode -n <namespace>
```

**3. Get the RPC secret:**

```bash
kubectl get secret <release-name>-rpc-secret -n <namespace> \
  -o jsonpath='{.data.rpcSecret}' | base64 -d
```

**4. Run a command:**

```bash
garage \
  -h <full-node-id>@127.0.0.1:3901 \
  -s <rpc-secret> \
  status
```

> Note: port 3901 is not declared in the pod spec (it's internal RPC only), but `kubectl port-forward` works regardless.

### Provisioning a bucket

After a fresh install, assign the layout before creating buckets:

```bash
# Assign the node to a zone with capacity in KiB (102400 KiB = 100 MiB)
garage ... layout assign -z dc1 -c 102400 <full-node-id>
garage ... layout apply

# Create a bucket
garage ... bucket create <bucket-name>

# Create an access key
garage ... key create <key-name>

# Grant the key access to the bucket (bucket name is positional, before flags)
garage ... bucket allow <bucket-name> --key <key-name> --read --write

# Show the access key ID and secret
garage ... key info <key-name>
```

### Using the admin REST API

The admin API (port 3903) requires a Bearer token. Retrieve it and port-forward:

```bash
ADMIN_TOKEN=$(kubectl get secret <release-name>-rpc-secret -n <namespace> \
  -o jsonpath='{.data.adminToken}' | base64 -d)

kubectl port-forward -n <namespace> <pod-name> 3903:3903
```

> Note: port 3903 is not declared in the pod spec but `kubectl port-forward` works regardless.

The admin API uses `/v2/` endpoints in Garage v2.4.x:

```bash
# Cluster status
curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" http://localhost:3903/v2/GetClusterStatus | jq .

# List buckets
curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" http://localhost:3903/v2/ListBuckets | jq .

# List keys
curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" http://localhost:3903/v2/ListKeys | jq .
```

### Connecting with an S3 client

Bucket credentials are stored in a Kubernetes Secret after provisioning (see [Provisioning](#provisioning-a-bucket)). Retrieve them and use any S3-compatible client:

```bash
ACCESS_KEY=$(kubectl get secret <release-name>-<bucket>-credentials -n <namespace> \
  -o jsonpath='{.data.access_key}' | base64 -d)
SECRET_KEY=$(kubectl get secret <release-name>-<bucket>-credentials -n <namespace> \
  -o jsonpath='{.data.secret_key}' | base64 -d)
```

Port-forward the S3 API port:

```bash
kubectl port-forward -n <namespace> <pod-name> 3900:3900
```

**Using the AWS CLI** (`pip install awscli`):

```bash
# One-off
AWS_ACCESS_KEY_ID=$ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$SECRET_KEY \
aws --endpoint-url http://localhost:3900 --region garage s3 ls

# Or save as a named profile
aws configure --profile <profile-name>
# Access Key ID:     <access_key>
# Secret Access Key: <secret_key>
# Default region:    garage

aws --profile <profile-name> --endpoint-url http://localhost:3900 s3 ls
aws --profile <profile-name> --endpoint-url http://localhost:3900 s3 ls s3://<bucket>
aws --profile <profile-name> --endpoint-url http://localhost:3900 s3 cp myfile.txt s3://<bucket>/
```

### Stale GarageNode CRDs

Every Garage node registers itself as a `GarageNode` CRD on startup. If you reinstall without cleaning these up, the new node will try to connect to the stale entries and log RPC errors. Clean them up with:

```bash
kubectl delete garagenode --all -n <namespace>
```

This is handled automatically by the pre-delete Helm hook on `helm uninstall`.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` |  |
| args | list | `[]` | Override the container arguments. |
| command | list | `[]` | Override the container entrypoint. |
| commonLabels | object | `{}` | Additional labels to add to all resources created by this chart |
| deployment.kind | string | `"StatefulSet"` | Switchable to DaemonSet |
| deployment.podManagementPolicy | string | `"OrderedReady"` | If using statefulset, allow Parallel or OrderedReady (default) |
| deployment.replicaCount | int | `3` | Number of StatefulSet replicas/garage nodes to start |
| environment | object | `{}` | Extra container env vars, as a list of {name, value} objects (same shape as a Pod container's env) |
| extraVolumeMounts | object | `{}` | Extra volume mounts, as a list of mount objects (same shape as a container's volumeMounts) |
| extraVolumes | object | `{}` | Extra volumes, as a list of volume objects (same shape as a PodSpec's volumes) |
| fullnameOverride | string | `""` |  |
| garage.additionalTopLevelConfig | string | `""` | Additional configuration to append to garage.toml. Use a multi-line string for custom config. Example:  additionalTopLevelConfig: |-    data_fsync = true |
| garage.admin.apiBindAddr | string | `"[::]:3903"` |  |
| garage.blockSize | string | `"1048576"` | Defaults is 1MB, an increase can result in better performance in certain scenarios https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/#block_size |
| garage.bootstrapPeers | list | `[]` | This is not required if you use the integrated kubernetes discovery |
| garage.compressionLevel | string | `"1"` | zstd compression level of stored blocks https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/#compression_level |
| garage.consistencyMode | string | `"consistent"` | By default, enable read-after-write consistency guarantees, see the consistency_mode section at https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/#consistency_mode |
| garage.dbEngine | string | `"lmdb"` | Can be changed for better performance on certain systems, use "sqlite" to prioritize durability https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/#db_engine |
| garage.existingConfigMap | string | `""` | if not empty string, allow using an existing ConfigMap for the garage.toml, if set, ignores garage.toml |
| garage.existingRpcSecret | string | `""` | If you want to provide an rpcSecret within an existing k8s secret, specify the secret name here, and store the value under the secret key `rpcSecret` the default secret will not be created |
| garage.garageTomlString | string | `""` | String Template for the garage configuration if set, ignores above values. Values can be templated, see https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/ |
| garage.kubernetesSkipCrd | bool | `false` | Set to true if you want to use k8s discovery but install the CRDs manually outside of the helm chart, for example if you operate at namespace level without cluster resources |
| garage.metadataAutoSnapshotInterval | string | `""` | If this value is set, Garage will automatically take a snapshot of the metadata DB file at a regular interval and save it in the metadata directory. https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/#metadata_auto_snapshot_interval |
| garage.noClusterRole | bool | `false` | Set to true if you want to use roles instead of cluster roles |
| garage.replicationFactor | string | `"3"` | Default to 3 replicas, see the replication_factor section at https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/#replication_factor |
| garage.rpcBindAddr | string | `"[::]:3901"` | Port used for node-to-node RPC |
| garage.rpcSecret | string | `""` | If not given, a random secret will be generated and stored in a Secret object |
| garage.s3.api.bindAddr | string | `"[::]:3900"` |  |
| garage.s3.api.region | string | `"garage"` |  |
| garage.s3.api.rootDomain | string | `".s3.garage.tld"` |  |
| garage.s3.web.bindAddr | string | `"[::]:3902"` |  |
| garage.s3.web.index | string | `"index.html"` |  |
| garage.s3.web.rootDomain | string | `".web.garage.tld"` |  |
| garage.singleNode | bool | `false` | Start Garage with `--single-node`, run one StatefulSet replica, and render replication_factor = 1 in the generated garage.toml, if using garageTomlString or existingConfigMap, set replication_factor = 1 yourself. |
| image.pullPolicy | string | `"IfNotPresent"` |  |
| image.repository | string | `"dxflrs/amd64_garage"` | default to amd64 docker image |
| image.tag | string | `""` | set the image tag, please prefer using the chart version and not this, to avoid compatibility issues |
| imagePullSecrets | list | `[]` | set if you need credentials to pull your custom image |
| ingress.s3.api.annotations | object | `{}` | Rely _either_ on the className or the annotation below but not both! If you want to use the className, set className: "nginx" and replace "nginx" by an Ingress controller name, examples [here](https://kubernetes.io/docs/concepts/services-networking/ingress-controllers). |
| ingress.s3.api.enabled | bool | `false` |  |
| ingress.s3.api.hosts[0] | object | `{"host":"s3.garage.tld","paths":[{"path":"/","pathType":"Prefix"}]}` | garage S3 API endpoint, to be used with awscli for example |
| ingress.s3.api.hosts[1] | object | `{"host":"*.s3.garage.tld","paths":[{"path":"/","pathType":"Prefix"}]}` | garage S3 API endpoint, DNS style bucket access |
| ingress.s3.api.labels | object | `{}` |  |
| ingress.s3.api.tls | list | `[]` |  |
| ingress.s3.web.annotations | object | `{}` | Rely _either_ on the className or the annotation below but not both! If you want to use the className, set className: "nginx" and replace "nginx" by an Ingress controller name, examples [here](https://kubernetes.io/docs/concepts/services-networking/ingress-controllers). |
| ingress.s3.web.enabled | bool | `false` |  |
| ingress.s3.web.hosts[0] | object | `{"host":"*.web.garage.tld","paths":[{"path":"/","pathType":"Prefix"}]}` | wildcard website access with bucket name prefix |
| ingress.s3.web.hosts[1] | object | `{"host":"mywebpage.example.com","paths":[{"path":"/","pathType":"Prefix"}]}` | specific bucket access with FQDN bucket |
| ingress.s3.web.labels | object | `{}` |  |
| ingress.s3.web.tls | list | `[]` |  |
| initImage.pullPolicy | string | `"IfNotPresent"` |  |
| initImage.repository | string | `"busybox"` |  |
| initImage.tag | string | `"stable"` |  |
| livenessProbe | object | `{}` | Specifies a livenessProbe |
| monitoring.metrics.enabled | bool | `false` | If true, a service for monitoring is created with a prometheus.io/scrape annotation |
| monitoring.metrics.serviceMonitor.enabled | bool | `false` | If true, a ServiceMonitor CRD is created for a prometheus operator https://github.com/coreos/prometheus-operator |
| monitoring.metrics.serviceMonitor.interval | string | `"15s"` |  |
| monitoring.metrics.serviceMonitor.labels | object | `{}` |  |
| monitoring.metrics.serviceMonitor.path | string | `"/metrics"` |  |
| monitoring.metrics.serviceMonitor.relabelings | list | `[]` |  |
| monitoring.metrics.serviceMonitor.scheme | string | `"http"` |  |
| monitoring.metrics.serviceMonitor.scrapeTimeout | string | `"10s"` |  |
| monitoring.metrics.serviceMonitor.tlsConfig | object | `{}` |  |
| monitoring.tracing.sink | string | `""` | specify a sink endpoint for OpenTelemetry Traces, eg. `http://localhost:4317` |
| nameOverride | string | `""` |  |
| nodeSelector | object | `{}` |  |
| persistence.data.hostPath | string | `"/var/lib/garage/data"` |  |
| persistence.data.size | string | `"100Mi"` |  |
| persistence.enabled | bool | `true` |  |
| persistence.meta.hostPath | string | `"/var/lib/garage/meta"` |  |
| persistence.meta.size | string | `"100Mi"` |  |
| podAnnotations | object | `{}` | additional pod annotations |
| podSecurityContext.fsGroup | int | `1000` |  |
| podSecurityContext.fsGroupChangePolicy | string | `"OnRootMismatch"` |  |
| podSecurityContext.runAsGroup | int | `1000` |  |
| podSecurityContext.runAsNonRoot | bool | `true` |  |
| podSecurityContext.runAsUser | int | `1000` |  |
| priorityClassName | string | `""` | Optional priority class name to assign to the pods. See https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/ |
| readinessProbe | object | `{}` | Specifies a readinessProbe |
| resources | object | `{}` |  |
| securityContext.capabilities | object | `{"drop":["ALL"]}` | The default security context is heavily restricted, feel free to tune it to your requirements |
| securityContext.readOnlyRootFilesystem | bool | `true` |  |
| service.annotations | object | `{}` | Annotations to add to the service |
| service.s3.api.port | int | `3900` |  |
| service.s3.web.port | int | `3902` |  |
| service.type | string | `"ClusterIP"` | You can rely on any service to expose your cluster - ClusterIP (+ Ingress) - NodePort (+ Ingress) - LoadBalancer |
| serviceAccount.annotations | object | `{}` | Annotations to add to the service account |
| serviceAccount.create | bool | `true` | Specifies whether a service account should be created |
| serviceAccount.name | string | `""` | The name of the service account to use. If not set and create is true, a name is generated using the fullname template |
| tolerations | list | `[]` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
