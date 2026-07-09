"""Kubernetes access layer for the ClickHouse manager.

Source of truth for "managed installations" is a set of ConfigMaps (one per
installation) labelled with MANAGED_BY. Each stores the values subset the user
submitted, so we can re-render the chart for edits and deletes.
"""
import datetime as _dt
import json
import logging

import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient

log = logging.getLogger("chmanager.k8s")

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
                "apply_log": None,
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
    try:
        apply_log = json.loads(cm.data.get("apply_log.json", "null"))
    except (TypeError, json.JSONDecodeError):
        apply_log = None
    return {
        "release": release,
        "namespace": namespace,
        "values": values,
        "apply_log": apply_log,
        "status": get_chi_status(release, namespace),
    }


def save_values(release, namespace, values):
    data = {"release": release, "values.yaml": yaml.safe_dump(values)}
    # Preserve apply_log if it already exists on the CM.
    try:
        existing = _core.read_namespaced_config_map(_values_cm_name(release), namespace)
        if existing.data and existing.data.get("apply_log.json"):
            data["apply_log.json"] = existing.data["apply_log.json"]
    except ApiException as exc:
        if exc.status != 404:
            raise
    body = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=_values_cm_name(release),
            namespace=namespace,
            labels={LABEL_MANAGED: MANAGED_BY},
        ),
        data=data,
    )
    try:
        _core.replace_namespaced_config_map(_values_cm_name(release), namespace, body)
    except ApiException as exc:
        if exc.status == 404:
            _core.create_namespaced_config_map(namespace, body)
        else:
            raise


def save_apply_log(release, namespace, entries):
    """Persist the most recent apply log (list of {kind, name, namespace, action})."""
    payload = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "entries": entries,
    }
    patch = {"data": {"apply_log.json": json.dumps(payload)}}
    try:
        _core.patch_namespaced_config_map(_values_cm_name(release), namespace, patch)
    except ApiException as exc:
        log.warning("save_apply_log failed: %s", exc.reason)


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

def apply_manifests(manifests, namespace, release=None):
    """Create-or-update each rendered manifest through the Kubernetes API."""
    results = []
    for m in manifests:
        if release:
            _stamp_helm_metadata(m, release, namespace)
        results.append(_apply_one(m, namespace))
    return results


def _stamp_helm_metadata(manifest, release, namespace):
    """Stamp the labels/annotations Helm uses to identify managed resources.

    This makes objects adoptable by `helm upgrade --take-ownership`. It does NOT
    create a release Secret, so `helm ls` still won't list them.
    """
    meta = manifest.setdefault("metadata", {})
    labels = meta.setdefault("labels", {}) or {}
    labels["app.kubernetes.io/managed-by"] = "Helm"
    meta["labels"] = labels
    annotations = meta.setdefault("annotations", {}) or {}
    annotations["meta.helm.sh/release-name"] = release
    annotations["meta.helm.sh/release-namespace"] = namespace
    meta["annotations"] = annotations


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
        log.info("k8s delete (Job pre-recreate): %s/%s in %s", kind, name, ns)
        res.delete(name=name, namespace=ns)
        exists = False

    if exists:
        log.info("k8s patch: %s/%s in %s", kind, name, ns)
        res.patch(
            body=manifest,
            name=name,
            namespace=ns,
            content_type="application/merge-patch+json",
        )
        action = "updated"
    else:
        log.info("k8s create: %s/%s in %s", kind, name, ns)
        res.create(body=manifest, namespace=ns)
        action = "created"
    return {"apiVersion": api_version, "kind": kind, "name": name, "namespace": ns, "action": action}


def resource_exists(api_version, kind, name, namespace):
    """Best-effort check: is this resource still present in the cluster?"""
    try:
        res = _dyn.resources.get(api_version=api_version, kind=kind)
        ns = namespace if res.namespaced else None
        res.get(name=name, namespace=ns)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        log.warning("resource_exists error for %s/%s: %s", kind, name, exc.reason)
        return None
    except Exception as exc:
        log.warning("resource_exists error for %s/%s: %s", kind, name, exc)
        return None


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
            log.info("k8s delete: %s/%s in %s", kind, name, ns)
            res.delete(name=name, namespace=ns)
            results.append(f"{kind}/{name} deleted")
        except ApiException as exc:
            if exc.status != 404:
                log.warning("k8s delete failed: %s/%s: %s", kind, name, exc.reason)
                results.append(f"{kind}/{name} error: {exc.reason}")
    return results
