# ClickHouse on Kubernetes demo. `make help` for targets.
SHELL := /bin/bash
S := scripts

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

test:            ## offline tests: values.yaml vs chart + CRDs, SQL via chdb
	python3 -m pytest
test-live:       ## smoke tests against the running cluster
	DEMO_LIVE=1 python3 -m pytest

prereqs:         ## check docker/minikube/kubectl/helm
	$(S)/00-prereqs.sh
setup: prereqs   ## cluster, operator, helm install (keeper+clickhouse), data (before the talk)
	$(S)/01-cluster-up.sh && $(S)/install-operator.sh && $(S)/02-helm-install.sh && $(S)/03-load-data.sh
operator:        ## install the operator from ../helm/clickhouse-operator (once per cluster)
	$(S)/install-operator.sh
render:          ## show the CHI/CHK Helm renders from helm/values.yaml
	$(S)/render.sh
queries:         ## run the analytic queries
	$(S)/run-queries.sh
watch:           ## availability loop (second terminal)
	$(S)/watch-availability.sh
scale-shards:    ## 2 -> 3 shards
	$(S)/04-scale.sh shards 3
scale-replicas:  ## 2 -> 3 replicas
	$(S)/04-scale.sh replicas 3
config:          ## live profile change via helm upgrade, no restarts
	$(S)/05-live-config.sh
rollback:        ## helm rollback the config change
	$(S)/06-rollback.sh
upgrade:         ## rolling upgrade 24.8 -> 25.3
	$(S)/07-rolling-upgrade.sh
chaos:           ## delete a pod, watch it heal
	$(S)/08-chaos.sh
monitoring:      ## optional Prometheus + Grafana
	$(S)/optional-monitoring.sh
reset:           ## back to helm/values.yaml (2x2 / 24.8) between rehearsals
	$(S)/reset.sh
down:            ## delete the minikube cluster
	$(S)/99-teardown.sh

.PHONY: help test test-live prereqs setup operator render queries watch scale-shards scale-replicas config rollback upgrade chaos monitoring reset down
