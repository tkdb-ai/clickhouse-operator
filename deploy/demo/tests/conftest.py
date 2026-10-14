import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

DEMO_DIR = pathlib.Path(__file__).resolve().parents[1]
VALUES = DEMO_DIR / "helm" / "values.yaml"
# The chart and the operator chart (with its CRDs) both live in this repo.
CHART = DEMO_DIR.parent / "helm" / "clickhouse-helm-chart"
OPERATOR_CHART = DEMO_DIR.parent / "helm" / "clickhouse-operator"
RELEASE = "demo"
NAMESPACE = "ch-demo"


def load_yaml(rel: str) -> dict:
    return yaml.safe_load((DEMO_DIR / rel).read_text())


def helm_bin() -> str | None:
    return os.environ.get("HELM") or shutil.which("helm")


def render(*args: str) -> dict[str, dict]:
    """`helm template` the demo release; returns {kind: document}."""
    helm = helm_bin()
    if not helm:
        pytest.skip("helm not installed (set HELM=/path/to/helm)")
    out = subprocess.run(
        [helm, "template", RELEASE, str(CHART), "-n", NAMESPACE, "-f", str(VALUES), *args],
        capture_output=True, text=True, check=True,
    ).stdout
    return {d["kind"]: d for d in yaml.safe_load_all(out) if d}


@pytest.fixture(scope="session")
def values() -> dict:
    return yaml.safe_load(VALUES.read_text())


@pytest.fixture(scope="session")
def rendered() -> dict[str, dict]:
    return render()


@pytest.fixture(scope="session")
def chi(rendered) -> dict:
    return rendered["ClickHouseInstallation"]


@pytest.fixture(scope="session")
def chk(rendered) -> dict:
    return rendered["ClickHouseKeeperInstallation"]


def pytest_collection_modifyitems(config, items):
    """Live-cluster tests only run when asked for, so `pytest` is safe offline."""
    live = os.environ.get("DEMO_LIVE") == "1" or "cluster" in (config.getoption("-m") or "")
    if live:
        return
    skip = pytest.mark.skip(reason="live cluster tests: set DEMO_LIVE=1 or run `pytest -m cluster`")
    for item in items:
        if "cluster" in item.keywords:
            item.add_marker(skip)
