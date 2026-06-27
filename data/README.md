# Data Scripts

Scripts and sample data for loading test datasets into ClickHouse.

All scripts auto-detect the admin password from the `ch1-clickhouse-installation-admin`
Kubernetes secret when `kubectl` is configured, so no credentials are required in most cases.

## Scripts

### `load_trips.sh` — NYC Taxi trips

Loads the ClickHouse public NYC taxi sample dataset (~2M rows per file, 3 files total).

**Raw source:** 3 × ~82MB gzipped TSV files from the ClickHouse S3 sample bucket (~246MB total compressed, ~1.5GB uncompressed). Data covers July–September 2015.

```bash
# Load all 3 files (~6M rows)
./data/load_trips.sh

# Load only the first file (~2M rows)
./data/load_trips.sh --files 0

# Connect to a non-default host
./data/load_trips.sh --host 10.0.0.1 --port 9000 --user admin --password secret
```

Creates `testdb.trips` and `testdb.taxi_zone_dictionary` if they don't exist.

---

### `load_nessus.py` — Nessus vulnerability scan data

Parses one or more `.nessus` XML files and loads findings into `testdb.nessus_findings`.

```bash
# Load all sample files
python3 data/load_nessus.py data/nessus/*.nessus

# Replace existing data
python3 data/load_nessus.py data/nessus/*.nessus --truncate
```

---

### `export_nessus.py` — Export findings back to `.nessus` XML

Reconstructs `.nessus` XML files from the `nessus_findings` table in ClickHouse.
Useful for re-seeding the `data/nessus/` directory if it gets out of sync.

```bash
python3 data/export_nessus.py                  # exports to data/nessus/
python3 data/export_nessus.py --out /tmp/scans
```

---

### `generate_nessus_samples.py` — Generate synthetic Nessus test data

Creates two realistic `.nessus` sample files with a mix of Critical, High, Medium, and Low
findings across Windows and Linux hosts. Useful for testing load/query pipelines without
needing a real Nessus scanner.

```bash
python3 data/generate_nessus_samples.py
# Writes: data/nessus/sample_windows_network.nessus
#         data/nessus/sample_linux_web.nessus
```

---

## Sample Data (`data/nessus/`)

| File | Hosts | Findings | Notes |
|---|---|---|---|
| `nessus_sample_1.nessus` | 7 Windows hosts | 295 | Original sample — Medium severity only |
| `nessus_sample_2.nessus` | Various | 6 | Small supplemental sample |
| `sample_windows_network.nessus` | 6 Windows servers | 71 | Generated — includes Critical/High (EternalBlue, Badlock) |
| `sample_linux_web.nessus` | 6 Linux/web servers | 71 | Generated — includes Critical/High (OpenSSL RCE, EOL OS) |
