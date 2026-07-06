"""Render the clickhouse-installation Helm chart into manifests.

The chart stays the single source of truth for how form values become a
ClickHouseInstallation. We only ever run `helm template` (never install) and
apply the output through the Kubernetes API elsewhere.
"""
import os
import subprocess
import tempfile

import yaml

import schema as schema_mod

# Path to the clickhouse-installation chart. In the container the chart is
# copied to /chart; for local dev it defaults to the sibling chart directory.
CHART_PATH = os.environ.get(
    "CHART_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "clickhouse-helm-chart")),
)


def _coerce(field, form):
    """Read one schema field from the submitted form and coerce by type."""
    path = field["path"]
    ftype = field.get("type", "text")
    if ftype == "bool":
        return form.get(path) in ("on", "true", "1", True)
    raw = form.get(path)
    if ftype == "number":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return field.get("default", 0)
    # text / password / select
    if raw is None or (raw == "" and not field.get("allowEmpty")):
        return field.get("default", "")
    return raw


def build_values(form, schema=None):
    """Build chart values from the schema-driven form plus the Advanced box.

    Everything the GUI overrides is derived from fields.yaml, so exposing a new
    value is a schema edit — no code change here. Values not in the schema can
    still be supplied via the `_raw_yaml` Advanced box; structured fields win
    over the raw YAML on any overlapping path.
    """
    schema = schema or schema_mod.load_schema()
    values = {}
    for field in schema_mod.all_fields(schema):
        schema_mod.set_path(values, field["path"], _coerce(field, form))
    for path, val in (schema.get("constants") or {}).items():
        schema_mod.set_path(values, path, val)

    raw_yaml = (form.get("_raw_yaml") or "").strip()
    if raw_yaml:
        extra = yaml.safe_load(raw_yaml) or {}
        if not isinstance(extra, dict):
            raise RuntimeError("Advanced values must be a YAML mapping.")
        # structured fields override overlapping keys from the raw YAML
        values = schema_mod.deep_merge(extra, values)

    # The chart's default podTemplate wires S3 credentials from the garage-backup
    # secret. If garage is disabled that secret never exists, so clear those
    # references to avoid pods stuck referencing a missing secret.
    if not schema_mod.get_path(values, "garage.enabled", False):
        pod = values.setdefault("podTemplate", {})
        pod["extraEnv"] = None
        pod["extraVolumeMounts"] = None

    return values


def _is_test_hook(doc):
    """Skip helm test hooks — connectivity-test pods we never want to deploy."""
    annotations = (doc.get("metadata", {}) or {}).get("annotations", {}) or {}
    hook = annotations.get("helm.sh/hook", "")
    return "test" in hook


def render_manifests(release, namespace, values):
    """Return a list of manifest dicts from `helm template`.

    Raises RuntimeError with helm's stderr on failure.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(values, fh)
        values_file = fh.name
    try:
        result = subprocess.run(
            ["helm", "template", release, CHART_PATH, "-n", namespace, "-f", values_file],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "helm template failed")
        return [
            doc
            for doc in yaml.safe_load_all(result.stdout)
            if doc and not _is_test_hook(doc)
        ]
    finally:
        os.unlink(values_file)


def render_yaml(release, namespace, values):
    """Rendered manifests as a single YAML string (for the detail/preview view)."""
    docs = render_manifests(release, namespace, values)
    return "---\n".join(yaml.safe_dump(d, sort_keys=False) for d in docs)
