#!/usr/bin/env bash
# Check the laptop has what the demo needs.
source "$(dirname "$0")/lib.sh"
missing=0
for bin in docker minikube kubectl helm python3; do
  if command -v "$bin" >/dev/null; then
    printf '  ok      %-8s %s\n' "$bin" "$($bin version --short 2>/dev/null | head -1 || true)"
  else
    printf '  MISSING %s\n' "$bin"; missing=1
  fi
done
docker info >/dev/null 2>&1 || { echo "  docker daemon not running"; missing=1; }
mem_gb=$(docker info --format '{{.MemTotal}}' 2>/dev/null | awk '{printf "%d", $1/1024/1024/1024}')
echo "  docker memory: ${mem_gb:-?} GiB (minikube needs MINIKUBE_MEMORY x nodes: 9+ GiB by default)"
exit $missing
