"""Kubernetes access layer for the ClickHouse manager.

Source of truth for "managed installations" is a set of ConfigMaps (one per
installation) labelled with MANAGED_BY. Each stores the values subset the user
submitted, so we can re-render the chart for edits and deletes.
"""
import json

import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient

MANAGED_BY = "clickhouse-manager"
LABEL_MANAGED = "app.kubernetes.io/managed-by"
CHI_API = "clickhouse.altinity.com/v1"
CHI_KIND = "ClickHouseInstallation"


def _load_config():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


_load_config()
_api_client = client.ApiClient()
_dyn = DynamicClient(_api_client)
_core = client.CoreV1Api(_api_client)


def _values_cm_name(release):
    return f"chmanager-{release}"


# --- installation inventory (ConfigMap-backed) -----------------------------

def list_installations():
    """Return managed installations with their stored values and live CHI status."""
    cms = _core.list_config_map_for_all_namespaces(
        label_selector=f"{LABEL_MANAGED}={MANAGED_BY}"
    )
    installs = []
    for cm in cms.items:
        try:
            values = yaml.safe_load(cm.data.get("values.yaml", "")) or {}
        except yaml.YAMLError:
            values = {}
        release = cm.data.get("release", cm.metadata.name.replace("chmanager-", ""))
        namespace = cm.metadata.namespace
        installs.append(
            {
                "release": release,
                "namespace": namespace,
                "values": values,
                "status": get_chi_status(release, namespace),
            }
        )
    return sorted(installs, key=lambda i: (i["namespace"], i["release"]))


def get_installation(release, namespace):
    try:
        cm = _core.read_namespaced_config_map(_values_cm_name(release), namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    values = yaml.safe_load(cm.data.get("values.yaml", "")) or {}
    return {
        "release": release,
        "namespace": namespace,
        "values": values,
        "status": get_chi_status(release, namespace),
    }


def save_values(release, namespace, values):
    body = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=_values_cm_name(release),
            namespace=namespace,
            labels={LABEL_MANAGED: MANAGED_BY},
        ),
        data={"release": release, "values.yaml": yaml.safe_dump(values)},
    )
    try:
        _core.replace_namespaced_config_map(_values_cm_name(release), namespace, body)
    except ApiException as exc:
        if exc.status == 404:
            _core.create_namespaced_config_map(namespace, body)
        else:
            raise


def delete_values(release, namespace):
    try:
        _core.delete_namespaced_config_map(_values_cm_name(release), namespace)
    except ApiException as exc:
        if exc.status != 404:
            raise


# --- CHI status ------------------------------------------------------------

def get_chi_status(release, namespace):
    """Best-effort live status of the ClickHouseInstallation for a release."""
    name = _chi_name(release)
    try:
        res = _dyn.resources.get(api_version=CHI_API, kind=CHI_KIND)
        obj = res.get(name=name, namespace=namespace)
    except Exception:
        return {"phase": "Unknown", "hostsCompleted": None}
    status = (obj.to_dict() or {}).get("status", {}) or {}
    return {
        "phase": status.get("status", "—"),
        "hostsCompleted": status.get("hostsCompleted"),
        "hosts": status.get("hosts"),
    }


def _chi_name(release):
    # Mirrors the chart's clickhouse.fullname when nameOverride/fullnameOverride
    # are unset: the release name is used directly.
    return release


# --- apply / delete rendered manifests -------------------------------------

def apply_manifests(manifests, namespace):
    """Create-or-update each rendered manifest through the Kubernetes API."""
    results = []
    for m in manifests:
        results.append(_apply_one(m, namespace))
    return results


def _apply_one(manifest, default_ns):
    api_version = manifest["apiVersion"]
    kind = manifest["kind"]
    name = manifest["metadata"]["name"]
    res = _dyn.resources.get(api_version=api_version, kind=kind)
    ns = manifest["metadata"].get("namespace", default_ns) if res.namespaced else None
    if res.namespaced:
        manifest.setdefault("metadata", {})["namespace"] = ns

    exists = True
    try:
        res.get(name=name, namespace=ns)
    except ApiException as exc:
        if exc.status == 404:
            exists = False
        else:
            raise

    # Jobs (helm hooks) are largely immutable; recreate them on change.
    if kind == "Job" and exists:
        res.delete(name=name, namespace=ns)
        exists = False

    if exists:
        res.patch(
            body=manifest,
            name=name,
            namespace=ns,
            content_type="application/merge-patch+json",
        )
        return f"{kind}/{name} updated"
    res.create(body=manifest, namespace=ns)
    return f"{kind}/{name} created"


def delete_manifests(manifests, namespace):
    """Delete rendered manifests (reverse order so dependents go first)."""
    results = []
    for m in reversed(manifests):
        api_version = m["apiVersion"]
        kind = m["kind"]
        name = m["metadata"]["name"]
        try:
            res = _dyn.resources.get(api_version=api_version, kind=kind)
            ns = m["metadata"].get("namespace", namespace) if res.namespaced else None
            res.delete(name=name, namespace=ns)
            results.append(f"{kind}/{name} deleted")
        except ApiException as exc:
            if exc.status != 404:
                results.append(f"{kind}/{name} error: {exc.reason}")
    return results
