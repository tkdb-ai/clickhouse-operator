#!/usr/bin/env bash
source "$(dirname "$0")/lib.sh"
bold "Deleting minikube profile '$CLUSTER_NAME'"
minikube delete -p "$CLUSTER_NAME"
