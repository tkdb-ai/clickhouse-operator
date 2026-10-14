"""Live smoke tests against the minikube demo cluster.

    DEMO_LIVE=1 pytest            # or: pytest -m cluster

Run after 03-load-data.sh, and again after each demo step: the assertions are
written against whatever the CHI currently says, so they hold at 2x2, 3x2 or 3x3.
"""
import json
import os
import subprocess
import uuid

import pytest

pytestmark = pytest.mark.cluster

NS = os.environ.get("NS", "ch-demo")
CHI = os.environ.get("CHI", "demo")
RELEASE = os.environ.get("RELEASE", "demo")
CLUSTER = os.environ.get("CLUSTER", "main")       # the chart always names it "main"
KEEPER_CHK = os.environ.get("KEEPER_CHK", f"{CHI}-keeper")


def kubectl(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["kubectl", "-n", NS, *args], input=stdin, capture_output=True, text=True, check=True
    ).stdout


def ch(sql: str) -> str:
    """Query through the load-balanced Service, as an application would."""
    return kubectl(
        "exec", "-i", "ch-client", "--", "clickhouse-client",
        "--host", f"clickhouse-{CHI}", "--user", "demo", "--password", "demo",
        "--format", "TSV", "-q", sql,
    ).strip()


def rows(sql: str) -> list[list[str]]:
    out = ch(sql)
    return [line.split("\t") for line in out.splitlines()] if out else []


@pytest.fixture(scope="module")
def live_chi() -> dict:
    return json.loads(kubectl("get", "chi", CHI, "-o", "json"))


@pytest.fixture(scope="module")
def layout(live_chi) -> dict:
    return live_chi["spec"]["configuration"]["clusters"][0]["layout"]


def test_chi_is_managed_by_the_helm_release(live_chi):
    labels = live_chi["metadata"]["labels"]
    assert labels["app.kubernetes.io/managed-by"] == "Helm"
    assert labels["app.kubernetes.io/instance"] == RELEASE


def test_live_layout_matches_helm_values(layout):
    out = subprocess.run(
        ["helm", "get", "values", RELEASE, "-n", NS, "-a", "-o", "json"],
        capture_output=True, text=True, check=True,
    ).stdout
    ch_values = json.loads(out)["layout"]
    assert layout["shardsCount"] == int(ch_values["shardsCount"])
    assert layout["replicasCount"] == int(ch_values["replicasCount"])


def test_operator_reports_reconciled(live_chi):
    assert live_chi["status"]["status"] == "Completed"


def test_one_ready_pod_per_host(layout):
    pods = json.loads(kubectl("get", "pods", "-l", f"clickhouse.altinity.com/chi={CHI}", "-o", "json"))["items"]
    assert len(pods) == layout["shardsCount"] * layout["replicasCount"]
    for pod in pods:
        ready = {c["type"]: c["status"] for c in pod["status"]["conditions"]}["Ready"]
        assert ready == "True", pod["metadata"]["name"]


def test_clickhouse_sees_the_same_topology_as_kubernetes(layout):
    (shards, replicas) = rows(
        f"SELECT uniqExact(shard_num), max(replica_num) FROM system.clusters WHERE cluster = '{CLUSTER}'"
    )[0]
    assert int(shards) == layout["shardsCount"]
    assert int(replicas) == layout["replicasCount"]


def test_keeper_quorum_has_one_leader():
    pods = kubectl("get", "pods", "-l", f"clickhouse-keeper.altinity.com/chk={KEEPER_CHK}",
                   "-o", "jsonpath={.items[*].metadata.name}").split()
    assert len(pods) >= 3
    (zk_ok,) = rows("SELECT count() > 0 FROM system.zookeeper WHERE path = '/'")[0]
    assert zk_ok == "1"


def test_every_replica_of_a_shard_holds_the_same_rows():
    per_replica = rows(
        "SELECT getMacro('shard'), getMacro('replica'), count() "
        f"FROM clusterAllReplicas({CLUSTER}, demo.trips_local) GROUP BY 1, 2"
    )
    by_shard: dict[str, set[str]] = {}
    for shard, _replica, n in per_replica:
        by_shard.setdefault(shard, set()).add(n)
    assert by_shard, "no trips loaded: run scripts/03-load-data.sh"
    assert all(len(counts) == 1 for counts in by_shard.values()), by_shard


def test_distributed_total_equals_sum_of_shards():
    total = int(ch("SELECT count() FROM demo.trips"))
    per_shard = sum(int(n) for _, n in rows("SELECT _shard_num, count() FROM demo.trips GROUP BY 1"))
    assert total == per_shard > 0


def test_replication_is_healthy():
    bad = rows(
        "SELECT hostName(), table, is_readonly, absolute_delay, queue_size "
        f"FROM clusterAllReplicas({CLUSTER}, system.replicas) "
        "WHERE database = 'demo' AND (is_readonly OR absolute_delay > 30 OR queue_size > 100)"
    )
    assert bad == []


def test_insert_is_readable_through_the_service():
    marker = 4_000_000_000 + uuid.uuid4().int % 100_000_000   # above every real trip_id
    ch(
        "INSERT INTO demo.trips (trip_id, pickup_datetime, dropoff_datetime, passenger_count, "
        "trip_distance, fare_amount, extra, tip_amount, tolls_amount, total_amount, payment_type, "
        "pickup_ntaname, dropoff_ntaname) SETTINGS insert_distributed_sync = 1 "
        f"VALUES ({marker}, now(), now(), 1, 1, 5, 0, 1, 0, 6, 'CRE', 'Test', 'Test')"
    )
    assert ch(f"SELECT count() FROM demo.trips WHERE trip_id = {marker}") == "1"
    ch(f"ALTER TABLE demo.trips_local ON CLUSTER {CLUSTER} DELETE WHERE trip_id = {marker}")
