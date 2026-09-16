# Repository Directory Guide

This is the **Altinity Kubernetes Operator for ClickHouse** — a Go operator that creates, configures, and manages ClickHouse (and ClickHouse Keeper) clusters on Kubernetes via the `ClickHouseInstallation` (CHI) and `ClickHouseKeeperInstallation` (CHK) custom resources. This guide summarizes what each top-level directory contains.

## `cmd/`

Entry points for the two binaries this repo builds.

- `cmd/operator/` — the main operator binary. `main.go` / `app/main.go` wires up the controller-runtime machinery; `app/thread_chi.go` and `app/thread_keeper.go` run the CHI and CHK reconciliation loops as separate goroutines/threads. `app/fips_gate.go` and the `acvp_dispatch_*.go` files gate FIPS/ACVP crypto validation behavior behind build tags.
- `cmd/metrics_exporter/` — the metrics-exporter binary that scrapes ClickHouse and exposes Prometheus metrics. Mirrors the same FIPS/ACVP gating pattern as the operator.

## `pkg/`

The Go source tree — all core operator logic.

- `pkg/apis/` — CRD Go types (the API surface). `clickhouse.altinity.com/v1` defines the CHI and `ClickHouseInstallationTemplate` types; `clickhouse-keeper.altinity.com/v1` defines the CHK type; `common/types` holds shared spec types; `deployment/`, `metrics/`, `swversion/` hold smaller supporting types.
- `pkg/controller/` — reconciliation logic. `controller/chi/` reconciles ClickHouseInstallations (with `cmd_queue`, `kube`, `labeler`, `metrics` subpackages); `controller/chk/` reconciles ClickHouseKeeperInstallations; `controller/common/` holds shared reconciler pieces (`poller`, `statefulset`, `storage`, `announcer`).
- `pkg/model/` — translates CR specs into Kubernetes objects. `model/chi/` and `model/chk/` each have `creator` (builds StatefulSets/Services/ConfigMaps), `normalizer` (defaults/validates specs), `namer`/`macro` (naming and macro substitution), `config`, `tags`, `volume`; `model/common/` factors out shared logic between CHI and CHK; `model/clickhouse/` and `model/zookeeper/` hold client/version logic for those systems; `model/managers/` and `model/k8s/` hold higher-level orchestration and k8s object helpers.
- `pkg/chop/` — "ClickHouse Operator" runtime config: `chop.go`, `config_manager.go` (loads/watches operator config), `ipc_token.go` (inter-pod coordination tokens), `kube_machinery.go`, `restart.go`.
- `pkg/client/` — generated Kubernetes clientset/informers/listers for the CHI/CHK CRDs (standard `client-go` codegen output).
- `pkg/interfaces/` — shared Go interfaces (`interfaces-kube.go`, `interfaces-main.go`) and small typed enums (`label_type.go`, `service_type.go`, `volume_type.go`, etc.) used across packages to avoid import cycles.
- `pkg/metrics/` — `metrics/operator/` exposes the operator's own Prometheus metrics; `metrics/clickhouse/` is the metrics-exporter's core: `collector.go`, `exporter.go`, `rest_server.go`/`rest_client.go` (REST-based metrics fetch), `prometheus_writer.go`, `filters/`.
- `pkg/util/` — general utilities: `util/fips/` (FIPS 140-3 mode helpers, with `util/fips/acvp/` containing the ACVP wrapper repro harness described in its own README — gated behind `acvp_wrapper` build tag), `util/retry/`, `util/runtime/`, `util/tlsutil/`.
- `pkg/announcer/`, `pkg/xml/`, `pkg/version/` — small standalone helpers: structured event/log announcing, XML config manipulation, and version string handling, respectively.

## `config/`

Default runtime configuration shipped with the operator (mounted into the operator pod / used to seed ConfigMaps).

- `config/chi/` — default ClickHouse server config fragments (`config.d/*.xml` — listen, logger, query/part/trace log settings), default user profiles (`users.d/*.xml`), and example pod/storage/CHI templates (`templates.d/*.example`).
- `config/chk/` — the ClickHouse Keeper equivalents (`keeper_config.d/*.xml` for default keeper config, readiness, reconfig).
- `config/config.yaml` / `config/config-dev.yaml` / `config/secret.yaml` — top-level operator configuration files (prod and dev variants) and a secrets template.

## `deploy/`

Everything needed to install the operator and its ecosystem into a cluster, across several distribution mechanisms.

- `deploy/operator/` — the plain-manifest installer (`parts/`), the simplest "kubectl apply" install path.
- `deploy/helm/` — Helm charts: `clickhouse-operator/` (the operator's own chart, with `crds/`, `templates/`, `files/`), `clickhouse-helm-chart/` (a chart for deploying ClickHouse clusters themselves, with `templates/`, `tests/`, and an ad-hoc `chris/` subfolder that looks like a contributor's local working copy of a chart, not part of the published structure), and `clickhouse-manager/` (a separate app with its own `app/`, `docs/`, `deploy/`).
- `deploy/builder/` — shell scripts (`build-clickhouse-operator-install-yaml.sh`, etc.) and Jinja-style templates (`templates-install-bundle/`, `templates-config/`, `templates-operatorhub/`) that assemble the single-file install manifests and OperatorHub bundles from the Helm/config sources.
- `deploy/operatorhub/` — versioned OperatorHub.io bundle snapshots, one directory per released version (`0.18.1` … `0.27.1`), plus `metadata/`.
- `deploy/operator-web-installer/` — assets for the web-based "one-line install" page.
- `deploy/clickhouse-keeper/`, `deploy/zookeeper/`, `deploy/prometheus/`, `deploy/grafana/`, `deploy/garage/`, `deploy/openebs/` — reference manifests for deploying the coordination backend (Keeper or Zookeeper), monitoring stack, S3-compatible storage (garage), and local-PV storage (OpenEBS LVM) alongside the operator, either manually or via their own operators.
- `deploy/devspace/` — config for the `devspace` fast inner-dev-loop tool (see `devspace.yaml` at repo root and `docs/devspace.md`).

## `dockerfile/`

Container image build definitions: `dockerfile/operator/Dockerfile` and `dockerfile/metrics-exporter/Dockerfile`, plus `dockerfile/actions.secret` (encrypted secret used in CI image builds, managed via `.gitsecret`).

## `dev/`

Shell scripts for the day-to-day and release engineering workflow — not runtime code. Covers Go builds (`go_build_*.sh`), Docker image builds (`image_build_*.sh` for dev/universal/Altinity variants), code generation (`run_code_generator.sh`), linting/security (`run_vet.sh`, `run_gosec.sh`, `run_gocard.sh`), formatting checks (`find_unformatted_sources.sh`, `format_unformatted_sources.sh`), test running (`run_go_tests.sh`), Helm chart generation (`generate_helm_chart.sh`), and release cutting (`start_new_release_branch.sh`, `release_evidence.sh`, `build_hub_releases.sh`, `build_manifests.sh`).

## `hack/`

Small codegen support files: `boilerplate.go.txt` (license header template injected into generated files) and `tools.go` (blank-import pin for codegen tool dependencies, the standard Go pattern for tracking build-only tool versions in `go.mod`).

## `docs/`

User- and contributor-facing documentation (Markdown), the source for the published docs site.

- Top-level guides: `QUICKSTART.md`, `USER_GUIDE.md`, `architecture.md`, `custom_resource_explained.md`, `operator_installation_details.md`, `operator_configuration.md`, `operator_upgrade.md`, `operator_build_from_sources.md`, `replication_setup.md`, `zookeeper_setup.md`, `keeper_reference.md`, `keeper_migration_from_23_to_24.md`, `schema_migration.md`, `storage.md`, `monitoring_setup.md`/`MONITORING.md`, `prometheus_setup.md`, `grafana_setup.md`, `security_hardening.md`/`security_hardening_fips.md`, `fips_setup.md`/`fips_evidence_verification.md`, `chi_update_add_replication.md`, `chi_update_clickhouse_version.md`, `clickhouse_config_errors_handling.md`, `k8s_cluster_access.md`, `garage_access.md`, `devspace.md`, `CONNECTING.md`, `DISCONNECTED.md`, `start_new_release.md`, `pull_request_template.md`.
- `docs/chi-examples/` — sample `ClickHouseInstallation` YAML manifests, including `99-clickhouseinstallation-max.yaml` (the exhaustive reference example linked from the root README).
- `docs/chi-examples-withstand-errors/` — CHI examples specifically demonstrating error-tolerant/resilient configurations.
- `docs/chit-examples/` — `ClickHouseInstallationTemplate` examples.
- `docs/chk-examples/` — `ClickHouseKeeperInstallation` examples.
- `docs/img/` — diagrams and screenshots referenced by the docs.

## `grafana-dashboard/`

Standalone Grafana dashboard JSON exports: `Altinity_ClickHouse_Operator_dashboard.json`, `ClickHouse_Queries_dashboard.json`, `ClickHouseKeeper_dashboard.json`, `Zookeeper_dashboard.json`, `Kafka_dashboard.json`. Importable directly into Grafana.

## `tests/`

Test suites and test infrastructure.

- `tests/e2e/` — the main end-to-end suite, Python-based (`test_operator.py`, `test_metrics_exporter.py`, `test_acvp.py`, `steps.py`/`steps_fips.py`, helper modules `clickhouse.py`/`kubectl.py`/`yaml_manifest.py`/`settings.py`), plus shell runners for different modes (`run_tests_local.sh`, `run_tests_parallel.sh`, `run_tests_operator.sh`, `run_minikube_reset.sh`, `install_olm.sh`) and `tests/e2e/manifests/` with the CR fixtures used by the tests.
- `tests/docker-compose/` — Docker Compose setups for running dependencies (e.g. ClickHouse/Keeper) outside Kubernetes for lighter-weight testing.
- `tests/helpers/`, `tests/image/`, `tests/requirements/` — shared test helper code, test container image definitions, and Python dependency pinning for the e2e suite.

## `.github/`

GitHub Actions CI workflows (`build_branch.yaml`, `build_master.yaml`, `run_tests.yaml`, `check_helm.yaml`, `release_chart.yaml`, `cosign_sign.yaml`) plus `copilot-instructions.md` for repo-specific AI coding assistant guidance.

## Tooling / local state (not source)

- `.vagrant/` — local Vagrant VM state (machine metadata), generated by running `Vagrantfile`; not checked-in source of interest.
- `.gitsecret/` — `git-secret` keyring/config used to encrypt `dockerfile/actions.secret` and similar files for CI.

## Other files in repo root

Part of the operator project:

- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE` — standard project docs.
- `go.mod`, `go.sum` — Go module definition and dependency lockfile.
- `Vagrantfile` — spins up a local VM (used by some dev/test workflows, see `.vagrant/`).
- `devspace.yaml` — config for the `devspace` fast dev-loop tool (pairs with `deploy/devspace/`).

## User working files in repo root (not part of the operator source tree)

These appear to be the repo owner's personal scratch files unrelated to the ClickHouse operator project itself — likely just kept in this checkout for convenience:

- `nessus_findings.csv`, `nessus-rls.md` — Nessus vulnerability scan data/notes; matches the unrelated `data/nessus/` sample-data and loading scripts (`data/load_nessus.py`, `data/export_nessus.py`, `data/generate_nessus_samples.py`) described in `data/README.md`, which is itself a "Data Scripts" README for loading test datasets (NYC taxi + Nessus) into a ClickHouse instance — useful for demoing/testing against this operator's clusters, but not part of the operator's own source.
- `nyc-taxi-exploration.md` — notes related to the NYC taxi sample dataset, same `data/` tooling.
- `mcp-setup.md`, `setup-mcp.sh` — MCP (Model Context Protocol) server setup notes/script, unrelated to the operator.
- `ch.session.sql` — empty file, likely a scratch SQL session log.
- `release`, `releases` — small loose files (7 and 28 bytes) at the root; not part of the documented release tooling in `dev/`.
- `release_notes.md` — a large (33KB) release-notes file; worth checking whether this duplicates `CHANGELOG.md` or is separate scratch content.
