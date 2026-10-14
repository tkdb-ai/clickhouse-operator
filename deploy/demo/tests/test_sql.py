"""SQL checks with an embedded ClickHouse engine (chdb), no cluster needed.

Every statement in sql/ must parse, and the loader and analytic queries must
run against a local MergeTree copy of the schema, fed from a 1,000-row sample
of the real NYC taxi file (tests/fixtures/trips_sample.tsv, from trips_1.gz).
"""
import re

import pytest

from conftest import DEMO_DIR

chdb = pytest.importorskip("chdb")
from chdb import session as chs  # noqa: E402

SAMPLE = DEMO_DIR / "tests" / "fixtures" / "trips_sample.tsv"
SAMPLE_ROWS = 1000


def statements(name: str) -> list[str]:
    text = (DEMO_DIR / "sql" / name).read_text()
    parts = [p.strip() for p in text.split(";")]
    return [p for p in parts if any(l.strip() and not l.strip().startswith("--") for l in p.splitlines())]


ALL_SQL = [(n, s) for n in ("schema.sql", "load.sql", "queries.sql") for s in statements(n)]


@pytest.mark.parametrize("name, stmt", ALL_SQL, ids=[f"{n}#{i}" for i, (n, _) in enumerate(ALL_SQL)])
def test_statement_parses(name, stmt):
    sql = stmt.replace("__FILES__", "0..2").replace("'", "\\'")
    assert chdb.query(f"SELECT formatQuery('{sql}')", "TSV").bytes()


def test_loader_reads_the_public_taxi_bucket():
    load = statements("load.sql")[0]
    assert "s3('https://datasets-documentation.s3.eu-west-3.amazonaws.com/nyc-taxi/trips_{__FILES__}.gz'" in load


@pytest.fixture(scope="module")
def local_db():
    """Same columns and sort key as the cluster, minus replication/sharding,
    loaded with the real loader query pointed at the local sample file."""
    sess = chs.Session()
    ddl = statements("schema.sql")[1]
    ddl = ddl.replace(" ON CLUSTER main", "")
    ddl = re.sub(r"ReplicatedMergeTree\([^)]*\)", "MergeTree", ddl)
    ddl = ddl.replace("demo.trips_local", "demo.trips")
    sess.query("CREATE DATABASE IF NOT EXISTS demo")
    sess.query(ddl)
    load = statements("load.sql")[0]
    load = re.sub(r"s3\('[^']*'", f"file('{SAMPLE}'", load)
    load = load.replace(", insert_distributed_sync = 1", "")
    sess.query(load)
    yield sess
    sess.close()


def q(sess, sql: str) -> list[list[str]]:
    out = sess.query(sql, "TSV").bytes().decode().strip()
    return [line.split("\t") for line in out.splitlines()]


def query(n: int) -> str:
    return statements("queries.sql")[n - 1]


def test_loader_maps_every_sample_row(local_db):
    assert q(local_db, "SELECT count() FROM demo.trips") == [[str(SAMPLE_ROWS)]]


def test_loaded_values_look_like_taxi_trips(local_db):
    [[bad_times, neighborhoods, payment_types]] = q(
        local_db,
        "SELECT countIf(dropoff_datetime < pickup_datetime), uniqExact(pickup_ntaname), "
        "uniqExact(payment_type) FROM demo.trips",
    )
    assert bad_times == "0"
    assert int(neighborhoods) > 10
    assert int(payment_types) >= 2


def test_trips_by_hour_covers_the_day(local_db):
    hours = [int(h) for h, *_ in q(local_db, query(1))]
    assert hours == sorted(hours) and set(hours) <= set(range(24))


def test_top_neighborhoods_returns_ten(local_db):
    rows = q(local_db, query(2))
    assert len(rows) == 10
    counts = [int(trips) for _, trips, _ in rows]
    assert counts == sorted(counts, reverse=True)


def test_card_payers_tip_more_than_cash(local_db):
    tips = {ptype: float(pct) for ptype, _, pct in q(local_db, query(3))}
    assert tips["CRE"] > tips["CSH"]


def test_passenger_count_query_stays_in_range(local_db):
    assert {int(p) for p, *_ in q(local_db, query(4))} <= set(range(1, 7))
