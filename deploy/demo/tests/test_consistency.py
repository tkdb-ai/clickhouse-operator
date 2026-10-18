"""Offline checks that keep the demo kit, its docs and the charts in step.

Four groups: the demo values files render against the chart and the CRDs; the
docs name the operator version and the make targets that really exist; the shell
scripts parse; and the operator chart is told to watch the demo namespace.
"""
import copy
import re
import shutil
import subprocess

import jsonschema
import pytest
import yaml

from conftest import CHART, DEMO_DIR, NAMESPACE, OPERATOR_CHART, RELEASE, VALUES, helm_bin
from test_helm import CHI_CRD, CHK_CRD, chart_schema, crd_schema

# Both files describe a demo install. They differ on purpose (shard count, sizes),
# so only checks that hold for any valid install belong here.
CHART_DIR_VALUES = CHART / "values-demo.yaml"
VALUES_FILES = [pytest.param(VALUES, id="demo/helm/values.yaml"), pytest.param(CHART_DIR_VALUES, id="values-demo.yaml")]


def helm_template(chart, *args: str) -> list[dict]:
    helm = helm_bin()
    if not helm:
        pytest.skip("helm not installed (set HELM=/path/to/helm)")
    out = subprocess.run([helm, "template", RELEASE, str(chart), "-n", NAMESPACE, *args],
                         capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


# --- both demo values files against the chart and the CRDs -------------------

@pytest.mark.parametrize("path", VALUES_FILES)
def test_values_file_matches_chart_schema(path):
    jsonschema.validate(yaml.safe_load(path.read_text()), chart_schema())


@pytest.mark.parametrize("path", VALUES_FILES)
def test_values_file_renders_valid_chi_and_chk(path):
    docs = {d["kind"]: d for d in helm_template(CHART, "-f", str(path))}
    jsonschema.validate(docs["ClickHouseInstallation"], crd_schema(CHI_CRD))
    jsonschema.validate(docs["ClickHouseKeeperInstallation"], crd_schema(CHK_CRD))


@pytest.mark.parametrize("path", VALUES_FILES)
def test_values_file_uses_the_demo_names(path):
    docs = {d["kind"]: d for d in helm_template(CHART, "-f", str(path))}
    assert docs["ClickHouseInstallation"]["metadata"]["name"] == RELEASE
    assert docs["ClickHouseKeeperInstallation"]["metadata"]["name"] == f"{RELEASE}-keeper"


@pytest.mark.parametrize("path", VALUES_FILES)
def test_values_file_only_sets_keys_the_chart_knows(path):
    # Helm silently ignores a misspelt top-level key.
    known = set(yaml.safe_load((CHART / "values.yaml").read_text()))
    assert set(yaml.safe_load(path.read_text())) <= known


def test_schema_check_is_not_vacuous():
    bad = copy.deepcopy(yaml.safe_load(CHART_DIR_VALUES.read_text()))
    bad["layout"]["shardsCount"] = "two"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, chart_schema())


# --- docs against what exists ------------------------------------------------

DOCS = [DEMO_DIR / "README.md", DEMO_DIR / "SETUP.md", DEMO_DIR / "RUNSHEET.md"]
MAKEFILE = (DEMO_DIR / "Makefile").read_text()


def operator_version() -> str:
    chart = yaml.safe_load((OPERATOR_CHART / "Chart.yaml").read_text())
    assert chart["version"] == chart["appVersion"]
    return chart["appVersion"]


def test_docs_name_the_operator_version_in_this_repo():
    want = operator_version()
    for doc in DOCS:
        found = set(re.findall(r"\b0\.\d{2}\.\d+\b", doc.read_text()))
        assert found <= {want}, f"{doc.name} mentions {sorted(found - {want})}, the operator chart is {want}"


def test_make_targets_in_the_docs_exist():
    targets = set(re.findall(r"^([a-z-]+):", MAKEFILE, re.M))
    for doc in DOCS:
        for name in re.findall(r"`make ([a-z-]+)", doc.read_text()):
            assert name in targets, f"{doc.name}: `make {name}` is not a Makefile target"


def test_scripts_named_in_the_docs_exist():
    # Helper scripts that live at the repo root (setup-mcp.sh) are linked from SETUP.md too.
    scripts = {p.name for p in (DEMO_DIR / "scripts").iterdir()} | {p.name for p in DEMO_DIR.parents[1].glob("*.sh")}
    for doc in DOCS:
        for name in re.findall(r"`((?:\d\d-|[a-z-]+)[\w-]*\.sh)", doc.read_text()):
            assert name in scripts, f"{doc.name} names {name}, which is not in scripts/"


def test_relative_links_in_the_docs_resolve():
    for doc in DOCS:
        for target in re.findall(r"\]\((?!https?:|#)([^)#]+)", doc.read_text()):
            assert (doc.parent / target).exists(), f"{doc.name} links to missing {target}"


def test_docs_do_not_claim_zone_spreading_without_the_constraint():
    # The demo values set no topologySpreadConstraints, so the docs must not promise them.
    values = yaml.safe_load(VALUES.read_text())
    if values.get("layout", {}).get("topologySpreadConstraints"):
        return
    for doc in DOCS:
        assert not re.search(r"(?<!deliberately )spread across zones|spreads pods across zones", doc.read_text()), doc.name


# --- shell scripts -----------------------------------------------------------

SCRIPTS = sorted((DEMO_DIR / "scripts").glob("*.sh"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_parses(script):
    subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_is_executable_and_has_a_shebang(script):
    assert script.read_text().startswith("#!"), script.name
    assert script.stat().st_mode & 0o111 or script.name == "lib.sh", f"{script.name} is not executable"


def test_scripts_pass_shellcheck():
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    run = subprocess.run(["shellcheck", "-x", "-S", "warning", *map(str, SCRIPTS)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout


# --- the operator must watch the demo namespace ------------------------------

def watched_namespaces(*args: str) -> list[str]:
    for doc in helm_template(OPERATOR_CHART, *args):
        if doc["kind"] == "ConfigMap" and "config.yaml" in (doc.get("data") or {}):
            config = yaml.safe_load(doc["data"]["config.yaml"])
            if "watch" in config:
                return config["watch"]["namespaces"]["include"]
    pytest.fail("no operator ConfigMap with a watch section rendered")


def test_install_operator_script_watches_the_demo_namespace():
    # Keeper never comes up when the operator is cluster-wide or misses the namespace.
    assert NAMESPACE in watched_namespaces("--set", f"watchNamespaces={{{NAMESPACE}}}")


def test_install_operator_script_passes_that_override():
    script = (DEMO_DIR / "scripts" / "install-operator.sh").read_text()
    assert 'watchNamespaces={$NS}' in script


def test_operator_chart_default_is_documented():
    # This repo's operator chart defaults watchNamespaces to a fixed list. The demo
    # namespace is not in it, which is why SETUP.md says to always pass the override.
    default = watched_namespaces()
    setup = (DEMO_DIR / "SETUP.md").read_text()
    if NAMESPACE not in default:
        assert "does not include `ch-demo`" in setup
