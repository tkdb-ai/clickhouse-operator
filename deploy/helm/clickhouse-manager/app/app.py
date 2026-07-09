"""ClickHouse Manager — a small Flask GUI to create and manage ClickHouse
installations rendered from the clickhouse-installation Helm chart.
"""
import logging
import os

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

import chart
import k8s
import schema as schema_mod

# LOG_LEVEL=DEBUG surfaces the rendered values file contents as well.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("chmanager.app")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

DEFAULT_NAMESPACE = os.environ.get("DEFAULT_NAMESPACE", "default")


def _render_form(mode, release, namespace, values):
    """Render the create/edit form driven entirely by the schema."""
    schema = schema_mod.load_schema()
    return render_template(
        "form.html",
        mode=mode,
        release=release,
        namespace=namespace,
        schema=schema,
        values=schema_mod.field_values(schema, values or {}),
        extra_yaml=schema_mod.extra_yaml(schema, values or {}),
    )


@app.route("/")
def index():
    try:
        installs = k8s.list_installations()
        error = None
    except Exception as exc:  # surface cluster access problems in the UI
        installs, error = [], str(exc)
    return render_template("index.html", installs=installs, error=error, issues=schema_mod.schema_issues())


@app.route("/new")
def new():
    return _render_form("create", "", DEFAULT_NAMESPACE, {})


@app.route("/edit/<namespace>/<release>")
def edit(namespace, release):
    inst = k8s.get_installation(release, namespace)
    if not inst:
        flash(f"No managed installation {release} in {namespace}", "danger")
        return redirect(url_for("index"))
    return _render_form("edit", release, namespace, inst["values"])


@app.route("/apply", methods=["POST"])
def apply():
    mode = request.form.get("mode", "create")
    release = (request.form.get("release") or "").strip()
    namespace = (request.form.get("namespace") or DEFAULT_NAMESPACE).strip()
    log.info("apply: mode=%s release=%s namespace=%s", mode, release, namespace)

    if not release:
        log.warning("apply: missing release name")
        flash("Installation name is required.", "danger")
        return redirect(url_for("new"))

    try:
        values = chart.build_values(request.form)
    except Exception as exc:
        log.exception("apply: build_values failed")
        flash(f"Failed to build values: {exc}", "danger")
        return redirect(url_for("edit", namespace=namespace, release=release)
                        if mode == "edit" else url_for("new"))

    # Validate against the chart's values.schema.json, exactly as Helm would.
    errors = schema_mod.validate(values)
    if errors:
        log.warning("apply: schema validation failed (%d errors): %s", len(errors), errors[:5])
        flash("Validation failed: " + "; ".join(errors[:5]), "danger")
        return redirect(url_for("edit", namespace=namespace, release=release)
                        if mode == "edit" else url_for("new"))

    try:
        manifests = chart.render_manifests(release, namespace, values)
        results = k8s.apply_manifests(manifests, namespace, release=release)
        k8s.save_values(release, namespace, values)
        k8s.save_apply_log(release, namespace, results)
    except Exception as exc:
        log.exception("apply: %s %s failed", mode, release)
        flash(f"Failed to {mode} {release}: {exc}", "danger")
        target = "new" if mode == "create" else "edit"
        if mode == "edit":
            return redirect(url_for("edit", namespace=namespace, release=release))
        return redirect(url_for(target))

    log.info("apply: %s %s ok (%d resources)", mode, release, len(results))
    flash(
        f"{'Created' if mode == 'create' else 'Updated'} {release} "
        f"({len(results)} resources applied).",
        "success",
    )
    return redirect(url_for("detail", namespace=namespace, release=release))


@app.route("/detail/<namespace>/<release>")
def detail(namespace, release):
    inst = k8s.get_installation(release, namespace)
    if not inst:
        flash(f"No managed installation {release} in {namespace}", "danger")
        return redirect(url_for("index"))
    try:
        rendered = chart.render_yaml(release, namespace, inst["values"])
    except Exception as exc:
        rendered = f"# failed to render: {exc}"

    # Enrich the persisted apply log with live "does it still exist?" state.
    apply_log = inst.get("apply_log") or {}
    entries = list(apply_log.get("entries") or [])
    for e in entries:
        e["live"] = k8s.resource_exists(e["apiVersion"], e["kind"], e["name"], e.get("namespace") or namespace)
    apply_log_view = {"timestamp": apply_log.get("timestamp"), "entries": entries}

    return render_template("detail.html", inst=inst, rendered=rendered, apply_log=apply_log_view)


@app.route("/delete/<namespace>/<release>", methods=["POST"])
def delete(namespace, release):
    inst = k8s.get_installation(release, namespace)
    if not inst:
        flash(f"No managed installation {release} in {namespace}", "danger")
        return redirect(url_for("index"))
    try:
        manifests = chart.render_manifests(release, namespace, inst["values"])
        results = k8s.delete_manifests(manifests, namespace)
        k8s.delete_values(release, namespace)
        flash(f"Deleted {release} ({len(results)} resources).", "success")
    except Exception as exc:
        flash(f"Failed to delete {release}: {exc}", "danger")
    return redirect(url_for("index"))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
