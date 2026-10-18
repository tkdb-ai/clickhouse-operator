#!/usr/bin/env bash
# Check the laptop has what the demo needs.
source "$(dirname "$0")/lib.sh"
missing=0
# Each tool spells "print my version" differently; `<bin> version --short` only works for minikube and helm.
version_of() {
  case "$1" in
    docker)  docker version --format '{{.Client.Version}}' 2>/dev/null ;;
    kubectl) kubectl version --client -o yaml 2>/dev/null | awk '/gitVersion/ {print $2; exit}' ;;
    python3) python3 --version 2>&1 ;;
    *)       "$1" version --short 2>/dev/null ;;
  esac
}
for bin in docker minikube kubectl helm python3; do
  if command -v "$bin" >/dev/null; then
    printf '  ok      %-8s %s\n' "$bin" "$(version_of "$bin" | head -1)"
  else
    printf '  MISSING %s\n' "$bin"; missing=1
  fi
done
docker info >/dev/null 2>&1 || { echo "  docker daemon not running"; missing=1; }
mem_gb=$(docker info --format '{{.MemTotal}}' 2>/dev/null | awk '{printf "%d", $1/1024/1024/1024}')
echo "  docker memory: ${mem_gb:-?} GiB (minikube needs MINIKUBE_MEMORY x nodes: 9+ GiB by default)"
exit $missing
