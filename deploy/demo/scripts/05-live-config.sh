#!/usr/bin/env bash
# Change a user-profile setting with `helm upgrade`. ClickHouse hot-reloads
# users.d, so NO pod restarts: compare restart counts / pod ages before and after.
# --set-string keeps the number exact (Helm would turn 2000000000 into 2e+09).
source "$(dirname "$0")/lib.sh"
NEW="${1:-2000000000}"
bold "Before"
pod_ages
per_pod_setting
bold "Changing profiles.default/max_memory_usage -> $NEW"
# The chart takes flat "<profile>/<setting>" keys; "/" is fine inside a --set key.
helm_upgrade --set-string "profiles.default/max_memory_usage=$NEW"
wait_chi 300
bold "Waiting for kubelet to project the new ConfigMap and ClickHouse to reload it"
wait_setting "$NEW"
bold "After"
per_pod_setting
pod_ages
show helm history "$RELEASE" -n "$NS"
