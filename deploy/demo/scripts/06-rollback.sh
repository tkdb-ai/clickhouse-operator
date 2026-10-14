#!/usr/bin/env bash
# Every helm upgrade is a numbered release. Roll the last change back in one
# command; the operator reconciles the cluster to the previous values.
# Run straight after 05-live-config.sh: it reverts max_memory_usage, no restarts.
source "$(dirname "$0")/lib.sh"
show helm history "$RELEASE" -n "$NS"
bold "Rolling back to the previous release"
show helm rollback "$RELEASE" -n "$NS"
want=$(helm get values "$RELEASE" -n "$NS" -a -o json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['profiles']['default/max_memory_usage'])")
wait_chi 300
wait_setting "$want"
bold "After"
per_pod_setting
pod_ages
show helm history "$RELEASE" -n "$NS"
