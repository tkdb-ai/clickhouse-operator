# Demo run-sheet

Target: 30-minute slot, about 15 minutes of slides and 15 minutes live.
Font size 18+ in the terminal, dark theme, two panes side by side.

## The night before

1. `make setup` on the presenting laptop (see [SETUP.md](SETUP.md): creates the cluster, installs the operator,
   preloads images into every minikube node, loads ~3M taxi trips from S3). The data lives on the cluster's volumes, so
   venue Wi-Fi only matters for the extra files loaded in the scale-out step.
2. `make test && make test-live`: everything green.
3. Rehearse the stage steps once, then `make reset` to get back to `helm/values.yaml` (2x2 on 24.8).
4. Record a screen capture of the full run as a fallback video.

## 10 minutes before

* Docker running, `kubectl config current-context` is `ch-demo` (`minikube status -p ch-demo` all Running).
* `make test-live` green.
* Left pane: `cd deploy/demo`. Right pane: `make watch` (starts printing OK lines).
* If you'll query from Claude Code: the port-forward loop from SETUP.md step 5 is running.
* Close Slack and notifications.

## On stage

| Time | Do | Say | They should see |
|---|---|---|---|
| 0:00 | `kubectl get nodes -L topology.kubernetes.io/zone` | "Three minikube nodes on my laptop, pretending to be a 3-zone cloud." | 3 nodes, zone-a/b/c |
| 0:30 | `helm list -A`, then `cat helm/values.yaml` | "The operator is installed once, like any platform piece. Each database is one Helm release and one settings file: Keeper, 2 shards x 2 replicas, users, disks." | Two releases (operator, demo), short readable YAML |
| 1:30 | `kubectl -n ch-demo get chi,chk` | "Helm hands the operator two objects. The operator turns them into everything else." | One CHI, one CHK |
| 2:00 | `kubectl -n ch-demo get sts,pvc,svc,pods -o wide` | "From that one object: StatefulSets, volumes, Services, and pods spread across zones." | 4 CH pods + 3 Keeper pods on different nodes |
| 3:00 | `make queries` | "Millions of real New York taxi rides. When do people ride, where from, who tips? Every shard answers its slice at once. Queries 5 and 6 show where each trip lives and that the copies agree." | Fast results, even shard split |
| 5:00 | `make scale-shards` | "One value, `shardsCount` 2 to 3, one `helm upgrade`. Watch the right pane: never a FAIL." | New pods, system.clusters grows, new rows reach shard 3 |
| 8:00 | Point at the empty-shard note | "Kubernetes adds capacity. Data placement is still a database decision." | Shard 3 holds only new rows |
| 9:00 | `make config` | "Changing a memory limit across the fleet. Note the restart column, and that Helm just recorded this as a new release." | Value flips on every pod, RESTARTS unchanged, `helm history` grows |
| 10:00 | `make rollback` | "Didn't like it? One command back to the last good release." | Value flips back, RESTARTS unchanged |
| 11:00 | `make upgrade`, then go back to slides while it rolls | "New version is one value: the image tag. Rolling upgrade, one host at a time. The right pane keeps answering." | `ver=` in the right pane changes host by host |
| 14:00 | `make chaos` | "Let's break it. Delete a pod." | Pod Terminating, queries still OK, pod back, same PVC, same row count |
| 15:00 | `make test-live` | "And the same pytest suite I run in CI says it's healthy." | All green |

Optional if time allows: `make scale-replicas` (needs about 10 GB of Docker memory).

## If something goes wrong

* **A step hangs at `status=InProgress`**: `kubectl -n ch-demo logs -l app.kubernetes.io/name=altinity-clickhouse-operator -c clickhouse-operator --tail=50`.
  Narrate it: "this is the operator's reconcile log". Move on to the next step; reconciliation continues in the background.
* **Pods Pending**: Docker is out of memory. Skip `scale-replicas`; `kubectl describe pod` shows the scheduler event, a good teaching moment.
* **No internet at the venue**: the scale-out step normally loads two more taxi files from S3. Run `OFFLINE=1 make scale-shards` instead; it re-inserts 2M existing trips under new ids so the new shard still fills up.
* **`helm upgrade` seems to do nothing**: check `helm get values demo -n ch-demo`; a misspelt `--set` key is ignored silently (`make test` guards the scripted ones).
* **Image pull slow**: images were not preloaded. `scripts/01-cluster-up.sh` is idempotent: it reuses the running profile and loads the images again.
* **Pods stuck on a PVC**: `kubectl get sc` should show `local-path (default)`; rerun `scripts/01-cluster-up.sh`.
* **The right pane shows a FAIL or two during the upgrade**: expected if a query was in flight on the restarting pod. Say so; clients retry. Production would add `load_balancing` and retries in the driver.
* **Total failure**: switch to the recorded video.

## Afterwards

`make reset` to rehearse again, `make down` to delete everything (the whole
minikube profile, operator included). To remove only the database, run
`helm uninstall demo -n ch-demo` while the operator is still running, so the
CHI finalizer can finish.
