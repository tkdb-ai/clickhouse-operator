# GitHub Copilot Instructions for clickhouse-operator

- This repo builds the Altinity Kubernetes Operator for ClickHouse. The main runtime is `cmd/operator`, with a separate metrics exporter in `cmd/metrics_exporter`.
- The operator is not a small web service; it is a Kubernetes controller that watches CRDs under `clickhouse.altinity.com/v1` and manages ClickHouse clusters, pod templates, services, and Zookeeper keeper instances.
- Key code areas:
  - `cmd/operator/main.go` and `cmd/operator/app/main.go` are the application entrypoints.
  - `pkg/chop` contains operator runtime support, Kubernetes client initialization, and control loops.
  - `pkg/apis` contains the CRD type definitions for `ClickHouseInstallation`, `ClickHouseInstallationTemplate`, and `ClickHouseOperatorConfiguration`.
  - `pkg/client` contains generated clientset/informer/lister code. Do not edit generated files manually; use `./dev/run_code_generator.sh` when API types change.
  - `config/config-dev.yaml` is the default local development config; `config/config.yaml` is the production/default config template.

- Build and run workflows:
  - Build the operator: `./dev/go_build_operator.sh`
  - Build the metrics exporter: `./dev/go_build_metrics_exporter.sh`
  - Run the operator locally: `./dev/run_operator.sh` (uses `config/config-dev.yaml` by default and rebuilds the binary unless passed `nobuild`).
  - Run unit tests: `./dev/run_go_tests.sh` (`go test -vet=off ./...` by default).
  - Run static vet separately: `./dev/run_vet.sh`.
  - Regenerate Kubernetes client code and deepcopy helpers: `./dev/run_code_generator.sh`.

- Project conventions:
  - Binary metadata is injected from `release` and git SHA using `dev/go_build_universal.sh` and `pkg/version`.
  - The build scripts expect module-aware builds (`GO111MODULE=on`) and use `vendor` when available.
  - Local operator run uses command-line flags from `cmd/operator/app/main.go`: `-config`, `-master`, `-debug`, and `-version`.
  - Logging is centralized through `pkg/announcer` and `dev/run_operator.sh` uses `-alsologtostderr=true` and `-log_dir=log` for local debugging.
  - The repository uses `./dev/bin` for built binaries and cleans them after local runs via `dev/go_build_operator_clean.sh`.

- Testing and CI:
  - CI uses GitHub Actions in `.github/workflows`; `run_tests.yaml` runs Minikube-based integration tests in `tests/regression.py` and requires `clickhouse-client` plus `tfs`.
  - The repo’s integration tests are not just `go test`; they include cluster-level behavior with Prometheus, MinIO, and Zookeeper operator setup.
  - For code review, prefer fixes close to `pkg/chop` and `pkg/apis` rather than changing generated client code.

- Helpful project-specific notes:
  - Custom resource discovery is wired through `pkg/client/informers/externalversions/generic.go` and the CRD group `clickhouse.altinity.com`.
  - Helm packaging lives under `deploy/helm`; the main chart here is `deploy/helm/clickhouse-helm-chart`.
  - `release` contains the operator release version used by build scripts and Docker tags.
  - The operator itself launches three threads in `cmd/operator/app/main.go`: ClickHouse reconciler, reconciler metrics exporter, and keeper.

If any section is unclear or missing details, please tell me which area you want expanded so I can iterate.