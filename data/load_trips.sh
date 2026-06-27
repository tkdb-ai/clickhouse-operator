#!/usr/bin/env bash
# Load NYC taxi trips sample data into ClickHouse.
#
# Source: ClickHouse public S3 dataset (3 gzipped TSV files, ~82MB each / ~246MB total)
# Destination: testdb.trips (~6M rows when all 3 files loaded)
#
# Usage:
#   ./load_trips.sh                        # load all 3 files
#   ./load_trips.sh --files 0              # load only trips_0.gz (~2M rows)
#   ./load_trips.sh --host localhost --port 9000 --user admin --password secret
#
# Env overrides: CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_DATABASE

set -euo pipefail

CH_HOST="${CH_HOST:-localhost}"
CH_PORT="${CH_PORT:-9000}"
CH_USER="${CH_USER:-admin}"
CH_PASSWORD="${CH_PASSWORD:-$(kubectl get secret -A -o json 2>/dev/null \
  | python3 -c "import sys,json,base64; d=json.load(sys.stdin); items=[i for i in d['items'] if i['metadata']['name']=='ch1-clickhouse-installation-admin']; print(base64.b64decode(list(items[0]['data'].values())[0]).decode()) if items else print('')" 2>/dev/null || true)}"
CH_DATABASE="${CH_DATABASE:-testdb}"
FILES="0 1 2"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) CH_HOST="$2"; shift 2 ;;
    --port) CH_PORT="$2"; shift 2 ;;
    --user) CH_USER="$2"; shift 2 ;;
    --password) CH_PASSWORD="$2"; shift 2 ;;
    --database) CH_DATABASE="$2"; shift 2 ;;
    --files) FILES="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$CH_PASSWORD" ]] && { echo "error: CH_PASSWORD not set and could not be detected from kubectl" >&2; exit 1; }

CH="clickhouse client --host $CH_HOST --port $CH_PORT --user $CH_USER --password $CH_PASSWORD --database $CH_DATABASE"

S3_BASE="https://datasets-documentation.s3.eu-west-3.amazonaws.com/nyc-taxi"

echo "==> Creating testdb and trips table if not exists"
$CH --query "CREATE DATABASE IF NOT EXISTS $CH_DATABASE"
$CH --query "
CREATE TABLE IF NOT EXISTS trips (
    trip_id             UInt32,
    vendor_id           Enum8('1'=1,'2'=2,'3'=3,'4'=4,'CMT'=5,'VTS'=6,'DDS'=7,'B02512'=10,'B02598'=11,'B02617'=12,'B02682'=13,'B02764'=14,''=15),
    pickup_date         Date,
    pickup_datetime     DateTime,
    dropoff_date        Date,
    dropoff_datetime    DateTime,
    store_and_fwd_flag  UInt8,
    rate_code_id        UInt8,
    pickup_longitude    Float64,
    pickup_latitude     Float64,
    dropoff_longitude   Float64,
    dropoff_latitude    Float64,
    passenger_count     UInt8,
    trip_distance       Float64,
    fare_amount         Float32,
    extra               Float32,
    mta_tax             Float32,
    tip_amount          Float32,
    tolls_amount        Float32,
    ehail_fee           Float32,
    improvement_surcharge Float32,
    total_amount        Float32,
    payment_type        Enum8('UNK'=0,'CSH'=1,'CRE'=2,'NOC'=3,'DIS'=4),
    trip_type           UInt8,
    pickup              FixedString(25),
    dropoff             FixedString(25),
    cab_type            Enum8('yellow'=1,'green'=2,'uber'=3),
    pickup_nyct2010_gid  Int8,
    pickup_ctlabel      Float32,
    pickup_borocode     Int8,
    pickup_ct2010       String,
    pickup_boroct2010   String,
    pickup_cdeligibil   String,
    pickup_ntacode      FixedString(4),
    pickup_ntaname      String,
    pickup_puma         UInt16,
    dropoff_nyct2010_gid UInt8,
    dropoff_ctlabel     Float32,
    dropoff_borocode    UInt8,
    dropoff_ct2010      String,
    dropoff_boroct2010  String,
    dropoff_cdeligibil  String,
    dropoff_ntacode     FixedString(4),
    dropoff_ntaname     String,
    dropoff_puma        UInt16
) ENGINE = MergeTree
  PARTITION BY toYYYYMM(pickup_date)
  ORDER BY pickup_datetime
"

echo "==> Creating taxi_zone_dictionary if not exists"
$CH --query "
CREATE DICTIONARY IF NOT EXISTS taxi_zone_dictionary (
    LocationID  UInt16 DEFAULT 0,
    Borough     String,
    Zone        String,
    service_zone String
)
PRIMARY KEY LocationID
SOURCE(HTTP(URL '$S3_BASE/taxi_zone_lookup.csv' FORMAT 'CSVWithNames'))
LIFETIME(MIN 0 MAX 0)
LAYOUT(HASHED_ARRAY())
"

for i in $FILES; do
  URL="$S3_BASE/trips_${i}.gz"
  echo "==> Loading $URL"
  $CH --query "
    INSERT INTO trips
    SELECT * FROM url('$URL', 'TabSeparatedWithNames')
  "
  echo "    done: file $i"
done

echo "==> Row count:"
$CH --query "SELECT formatReadableQuantity(count()) as total_trips FROM trips"
