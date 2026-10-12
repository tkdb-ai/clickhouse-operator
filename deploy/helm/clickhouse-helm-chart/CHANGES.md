# Changes

Notable chart changes, newest first.

## Operator 0.27.4 + removal of `k8s_secret_*` user syntax

**Operator dependency:** `altinity-clickhouse-operator` bumped `0.27.3` -> `0.27.4`
(`Chart.yaml`, `Chart.lock`, `charts/`).

**Breaking (upstream):** operator 0.27.4 removed the `k8s_secret_*` /
`k8s_secret_env_*` user-settings syntax. A ClickHouseInstallation that uses it is
rejected with `RemovedSecretRefSyntax`.

**What changed in this chart** (`templates/chi.yaml`):

- The generated `admin` password and any user with `password_secret_name` now render
  as `valueFrom` / `secretKeyRef` instead of `<user>/k8s_secret_password`:

  ```yaml
  admin/password:
    valueFrom:
      secretKeyRef:
        name: <release>-admin     # or users.<name>.password_secret_name
        key: admin                # `password` for password_secret_name
  ```

- If a user sets both `password` and `password_secret_name`, the secret reference
  wins and the plaintext `password` is no longer emitted (they would otherwise be
  duplicate `<user>/password` keys).
- Setting any `users.<name>.k8s_secret_*` key in values now fails at render time with a
  message pointing at `password_secret_name`.
- Tests added in `tests/chi_test.yaml`.

**Upgrade notes**

- Existing releases: `helm upgrade` rewrites the CHI users to the new form; the
  referenced Secrets (`<release>-admin`, key `admin`; or your Secret, key `password`)
  are unchanged, so passwords do not change.
- If you run the operator separately, upgrade the chart before (or with) the operator;
  a 0.27.4 operator rejects CHIs rendered by older versions of this chart.
- Other upstream 0.27.4 behavior changes worth knowing: failed schema migrations now
  mark a CHI `Aborted` instead of `Completed`; Keeper rolling updates wait for Raft
  quorum; ZooKeeper endpoint changes no longer restart ClickHouse. The operator's
  CRD-install hook image is now `registry.k8s.io/kubectl:v1.36.3` (mirror it for
  air-gapped installs or set `operator.crdHook.enabled: false`).
- Full upstream notes: `CHANGELOG.md` at the repo root, section 0.27.4 (after merging
  upstream), or https://github.com/Altinity/clickhouse-operator/blob/master/CHANGELOG.md

**Not changed:** `templates/backup-cronjob.yaml` still uses `bitnami/kubectl:latest`.
