"""Offline checks on helm/values.yaml: run before every rehearsal, no cluster needed.

values.yaml is validated against the chart's own values.schema.json, then
rendered with `helm template` (this repo's deploy/helm/clickhouse-helm-chart) and
the resulting ClickHouseInstallation / ClickHouseKeeperInstallation are validated
against the operator's CRD schemas (deploy/helm/clickhouse-operator/crds). The
`helm upgrade --set` keys used by the demo scripts are checked to exist and to do
what the script says.
"""
import copy
import hashlib
import json
import re

import jsonschema
import pytest
import yaml

from conftest import CHART, DEMO_DIR, OPERATOR_CHART, render


def crd_schema(name: str) -> dict:
    crd = yaml.safe_load((OPERATOR_CHART / "crds" / f"CustomResourceDefinition-{name}.yaml").read_text())
    (version,) = [v for v in crd["spec"]["versions"] if v.get("storage")]
    return version["schema"]["openAPIV3Schema"]


CHI_CRD = "clickhouseinstallations.clickhouse.altinity.com"
CHK_CRD = "clickhousekeeperinstallations.clickhouse-keeper.altinity.com"
LIB = (DEMO_DIR / "scripts" / "lib.sh").read_text()


def lib_default(var: str) -> str:
    (value,) = re.findall(rf'{var}="\$\{{{var}:-([^}}]+)\}}"', LIB)
    return value


# --- values.yaml against the chart -------------------------------------------

def chart_schema() -> dict:
    return json.loads((CHART / "values.schema.json").read_text())


def test_values_match_chart_schema(values):
    jsonschema.validate(values, chart_schema())


def test_chart_schema_catches_a_typo(values):
    # Guard against the validation above passing vacuously.
    bad = copy.deepcopy(values)
    bad["layout"]["shardsCount"] = "two"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, chart_schema())


# --- what the chart renders --------------------------------------------------

def test_chart_renders_one_chi_and_one_chk(rendered):
    assert {"ClickHouseInstallation", "ClickHouseKeeperInstallation"} <= set(rendered)


def test_operator_is_not_part_of_the_release(values, rendered):
    # The operator is installed on its own first (SETUP.md); a second copy from
    # the subchart would fight it over the same CRDs.
    assert values["operator"]["enabled"] is False
    assert not any("operator" in d["metadata"]["name"] for d in rendered.values())


def test_chart_add_ons_are_off(rendered):
    # CH-UI is a :latest Deployment and stays off. Backup and Garage are on, so a
    # backup CronJob, the Garage StatefulSet and its setup hook Job are expected.
    assert "Deployment" not in rendered
    assert {"CronJob", "StatefulSet", "Job"} <= set(rendered)
    assert not any("ch-ui" in d["metadata"]["name"] for d in rendered.values())


def test_backup_is_on_alongside_clickhouse(values, chi):
    assert values["backup"]["enabled"] is True
    # Without Garage (or an external backup.s3 target) there is nowhere to upload to.
    assert values["garage"]["enabled"] is True
    (template,) = chi["spec"]["templates"]["podTemplates"]
    assert [c["name"] for c in template["spec"]["containers"]] == ["clickhouse", "clickhouse-backup"]


def test_no_cron_sidecar_in_the_clickhouse_pod(chi):
    # The chart's default cron-sidecar uses a locally built image minikube can't pull.
    (template,) = chi["spec"]["templates"]["podTemplates"]
    assert "cron-sidecar" not in [c["name"] for c in template["spec"]["containers"]]


def test_chi_matches_operator_crd(chi):
    jsonschema.validate(chi, crd_schema(CHI_CRD))


def test_chk_matches_operator_crd(chk):
    jsonschema.validate(chk, crd_schema(CHK_CRD))


def test_crd_schema_catches_a_typo(chi):
    bad = copy.deepcopy(chi)
    bad["spec"]["configuration"]["clusters"][0]["layout"]["shardsCount"] = "two"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, crd_schema(CHI_CRD))


def test_scripts_use_the_names_the_chart_generates(chi):
    # lib.sh builds pod names, labels and the Service name from these.
    assert chi["metadata"]["name"] == lib_default("CHI")
    assert lib_default("RELEASE") == "demo"


def test_keeper_has_an_odd_quorum_of_at_least_three(chk):
    replicas = chk["spec"]["configuration"]["clusters"][0]["layout"]["replicasCount"]
    assert replicas >= 3 and replicas % 2 == 1


def test_clickhouse_points_at_the_keeper(chi, chk):
    # The chart references the CHK by name; the operator resolves its Service.
    assert chi["spec"]["configuration"]["zookeeper"] == {"keeper": {"name": chk["metadata"]["name"]}}
    assert chk["metadata"]["name"] == lib_default("KEEPER_CHK").replace("$CHI", lib_default("CHI"))


def test_every_shard_is_replicated(chi):
    layout = chi["spec"]["configuration"]["clusters"][0]["layout"]
    assert layout["replicasCount"] >= 2
    assert layout["shardsCount"] >= 2


def test_numbers_render_as_plain_integers(chi):
    # Helm turns an unquoted 1000000000 into "1e+09", which ClickHouse rejects.
    conf = chi["spec"]["configuration"]
    for section in ("profiles", "settings"):
        for key, value in conf.get(section, {}).items():
            assert not re.fullmatch(r"[\d.]+e[+-]\d+", str(value)), f"{section}.{key}={value}"


def test_demo_user_password_matches_the_scripts(chi):
    (password,) = set(re.findall(r"--password (\w+)", LIB))
    expected = hashlib.sha256(password.encode()).hexdigest()
    assert chi["spec"]["configuration"]["users"]["demo/password_sha256_hex"] == expected


def test_cluster_traffic_uses_a_secret(chi):
    # Lets distributed queries run on every shard as the user who sent them.
    assert chi["spec"]["configuration"]["clusters"][0]["secret"] == {"auto": "true"}


def _images(doc: dict) -> list[str]:
    return [
        c["image"]
        for t in doc["spec"]["templates"]["podTemplates"]
        for c in t["spec"]["containers"]
    ]


@pytest.mark.parametrize("doc", ["chi", "chk"])
def test_images_are_pinned(doc, request):
    images = _images(request.getfixturevalue(doc))
    assert images
    for image in images:
        assert ":" in image and not image.endswith(":latest"), image


def test_client_pod_image_is_pinned():
    (image,) = re.findall(r'image:\s*"?([^"\s]+)', (DEMO_DIR / "manifests" / "client.yaml").read_text())
    assert ":" in image and not image.endswith(":latest")


def test_anti_affinity_fits_three_nodes(chi):
    # ClickHouseAntiAffinity is a required rule. Scoped to the whole CHI it allows
    # one pod per node, so 2x2 on 3 minikube nodes leaves a pod Pending. Scoped to
    # a shard it only keeps a shard's replicas apart.
    (template,) = chi["spec"]["templates"]["podTemplates"]
    assert template["podDistribution"] == [{"type": "ClickHouseAntiAffinity", "scope": "Shard"}]


def test_keeper_pods_prefer_different_nodes(chk):
    # One zone label per node, so different nodes means different zones.
    (template,) = chk["spec"]["templates"]["podTemplates"]
    (term,) = template["spec"]["affinity"]["podAntiAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"]
    assert term["podAffinityTerm"]["topologyKey"] == "kubernetes.io/hostname"


def test_sql_uses_the_cluster_the_chart_defines(chi):
    cluster = chi["spec"]["configuration"]["clusters"][0]["name"]
    text = (DEMO_DIR / "sql" / "schema.sql").read_text()
    schema = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))
    assert set(re.findall(r"ON CLUSTER (\w+)", schema)) == {cluster}
    assert f"Distributed({cluster}," in schema


# --- the helm upgrade steps the scripts run ----------------------------------

SET_KEY = re.compile(r'(?:--set(?:-string)?\s+"?|key=)((?:layout|image|profiles|coordination)\.[\w./]+)')


def _script_set_keys():
    for script in sorted((DEMO_DIR / "scripts").glob("*.sh")):
        for key in SET_KEY.findall(script.read_text()):
            yield script.name, key


def _has_path(doc: dict, dotted: str) -> bool:
    node = doc
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def test_demo_scripts_change_values():
    assert len(set(_script_set_keys())) >= 4


@pytest.mark.parametrize("script, key", sorted(set(_script_set_keys())))
def test_script_set_keys_exist(values, script, key):
    # A misspelt --set key is silently ignored by Helm: the demo step would do nothing.
    chart_defaults = yaml.safe_load((CHART / "values.yaml").read_text())
    assert _has_path(values, key) or _has_path(chart_defaults, key), key


def _layout(docs):
    return docs["ClickHouseInstallation"]["spec"]["configuration"]["clusters"][0]["layout"]


def test_scale_shards_step():
    assert _layout(render("--set", "layout.shardsCount=3"))["shardsCount"] == 3


def test_scale_replicas_step():
    assert _layout(render("--set", "layout.replicasCount=3"))["replicasCount"] == 3


def test_live_config_step():
    docs = render("--set-string", "profiles.default/max_memory_usage=2000000000")
    profiles = docs["ClickHouseInstallation"]["spec"]["configuration"]["profiles"]
    assert profiles["default/max_memory_usage"] == "2000000000"


def test_rolling_upgrade_step(chi):
    upgraded = render("--set-string", f"image.tag={lib_default('UPGRADE_TAG')}")
    # The backup sidecar has its own image; only the ClickHouse server moves.
    (image,) = [i for i in _images(upgraded["ClickHouseInstallation"]) if "clickhouse-server" in i]
    assert image == f"clickhouse/clickhouse-server:{lib_default('UPGRADE_TAG')}"
    assert image not in _images(chi)
    backup = lambda doc: [i for i in _images(doc) if "clickhouse-backup" in i]
    assert backup(upgraded["ClickHouseInstallation"]) == backup(chi)
    # Only the image moves: the layout is untouched.
    assert _layout(upgraded) == chi["spec"]["configuration"]["clusters"][0]["layout"]


def test_backup_image_is_preloaded_into_minikube(chi):
    # Otherwise the first pod start pulls it over venue Wi-Fi.
    cluster_up = (DEMO_DIR / "scripts" / "01-cluster-up.sh").read_text()
    (image,) = [i for i in _images(chi) if "clickhouse-backup" in i]
    assert image in cluster_up


def test_upgrade_target_is_preloaded_into_minikube():
    cluster_up = (DEMO_DIR / "scripts" / "01-cluster-up.sh").read_text()
    assert "clickhouse-server:${UPGRADE_TAG}" in cluster_up or (
        f"clickhouse-server:{lib_default('UPGRADE_TAG')}" in cluster_up
    )


@pytest.mark.parametrize("name", ["schema.sql", "load.sql", "queries.sql"])
def test_sql_comments_have_no_semicolons(name):
    # run-queries.sh and the tests split statements on ';'.
    for line in (DEMO_DIR / "sql" / name).read_text().splitlines():
        if line.lstrip().startswith("--"):
            assert ";" not in line, line
