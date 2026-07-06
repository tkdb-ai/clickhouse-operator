"""ClickHouse Manager — a small Flask GUI to create and manage ClickHouse
installations rendered from the clickhouse-installation Helm chart.
"""
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

    if not release:
        flash("Installation name is required.", "danger")
        return redirect(url_for("new"))

    values = chart.build_values(request.form)

    # Validate against the chart's values.schema.json, exactly as Helm would.
    errors = schema_mod.validate(values)
    if errors:
        flash("Validation failed: " + "; ".join(errors[:5]), "danger")
        return redirect(url_for("edit", namespace=namespace, release=release)
                        if mode == "edit" else url_for("new"))

    try:
        manifests = chart.render_manifests(release, namespace, values)
        results = k8s.apply_manifests(manifests, namespace)
        k8s.save_values(release, namespace, values)
    except Exception as exc:
        flash(f"Failed to {mode} {release}: {exc}", "danger")
        target = "new" if mode == "create" else "edit"
        if mode == "edit":
            return redirect(url_for("edit", namespace=namespace, release=release))
        return redirect(url_for(target))

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
    return render_template("detail.html", inst=inst, rendered=rendered)


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
