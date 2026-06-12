# Nessus Findings — ClickHouse Row Level Security Example

## Overview

Demonstrates loading Nessus vulnerability scan data into ClickHouse and applying
Row Level Security (RLS) so different users only see findings for hosts they own.

---

## Step 1 — Download Sample Nessus Data

```bash
mkdir -p ~/Downloads/nessus-samples
cd ~/Downloads/nessus-samples

# Two sample scans from DefectDojo's public test fixtures
curl -L -o nessus_sample_1.nessus \
  https://raw.githubusercontent.com/DefectDojo/sample-scan-files/master/nessus/nessus_v_unknown.nessus

curl -L -o nessus_sample_2.xml \
  https://raw.githubusercontent.com/DefectDojo/sample-scan-files/master/nessus/nessus-02_v_unknown.xml
```

---

## Step 2 — Create the ClickHouse Table

```sql
CREATE TABLE IF NOT EXISTS testdb.nessus_findings (
    scan_file       String,
    host            String,
    host_ip         String,
    os              String,
    port            UInt16,
    protocol        String,
    svc_name        String,
    severity        UInt8,         -- 0=Info, 1=Low, 2=Medium, 3=High, 4=Critical
    plugin_id       UInt32,
    plugin_name     String,
    plugin_family   String,
    synopsis        String,
    description     String,
    solution        String,
    risk_factor     String,
    plugin_output   String,
    cve             Array(String),
    cvss_base_score Float32,
    cvss_vector     String,
    plugin_pub_date Date,
    plugin_mod_date Date
) ENGINE = MergeTree()
ORDER BY (severity, plugin_id, host);
```

---

## Step 3 — Parse and Load with Python

Install the ClickHouse Python client:

```bash
pip3 install clickhouse-connect
```

Loader script: `~/Downloads/nessus-samples/load_nessus.py`

```bash
cd ~/Downloads/nessus-samples
python3 load_nessus.py
# Parses nessus_sample_1.nessus and nessus_sample_2.xml by default
# Pass filenames as args to load specific files: python3 load_nessus.py myscan.nessus
```

To reload clean (truncate first):

```python
import clickhouse_connect
client = clickhouse_connect.get_client(host='localhost', port=8123,
                                       username='admin', password='...')
client.command('TRUNCATE TABLE testdb.nessus_findings')
```

**Result:** 301 findings across 8 hosts from 2 scan files.

---

## Step 4 — Row Level Security

### Users and policies

```sql
-- Create users
CREATE USER qa_analyst       IDENTIFIED BY 'qa_pass123';
CREATE USER external_analyst IDENTIFIED BY 'ext_pass123';
CREATE USER security_admin   IDENTIFIED BY 'admin_pass123';

-- Grant SELECT
GRANT SELECT ON testdb.nessus_findings TO qa_analyst;
GRANT SELECT ON testdb.nessus_findings TO external_analyst;
GRANT SELECT ON testdb.nessus_findings TO security_admin;

-- Row policies
CREATE ROW POLICY qa_policy
    ON testdb.nessus_findings FOR SELECT
    USING host_ip LIKE '10.31.112.%'
    TO qa_analyst;

CREATE ROW POLICY external_policy
    ON testdb.nessus_findings FOR SELECT
    USING host_ip NOT LIKE '10.%'
    TO external_analyst;

CREATE ROW POLICY admin_policy
    ON testdb.nessus_findings FOR SELECT
    USING 1                          -- no filter, sees everything
    TO security_admin;
```

### Access matrix

| User | Policy Filter | Visible Hosts |
|---|---|---|
| `qa_analyst` | `host_ip LIKE '10.31.112.%'` | 7 QA hosts (qa3app01–09) |
| `external_analyst` | `host_ip NOT LIKE '10.%'` | 1 external host (preprod.boardvantage.net) |
| `security_admin` | `1` (none) | All 8 hosts |

### How ClickHouse RLS works

- `CREATE ROW POLICY` appends a `USING` filter to every `SELECT` for the named users
- Users cannot bypass the filter — it is applied server-side before results are returned
- A user with **no policy assigned gets no rows** (deny by default)
- Policies can be assigned to users or roles, and multiple policies can be stacked

### Tear down

```sql
DROP ROW POLICY IF EXISTS qa_policy       ON testdb.nessus_findings;
DROP ROW POLICY IF EXISTS external_policy ON testdb.nessus_findings;
DROP ROW POLICY IF EXISTS admin_policy    ON testdb.nessus_findings;
DROP USER IF EXISTS qa_analyst;
DROP USER IF EXISTS external_analyst;
DROP USER IF EXISTS security_admin;
```

---

## Vulnerability Summary (sample data)

| Risk | Findings | Hosts Affected | Unique Vulns | Max CVSS |
|---|---|---|---|---|
| Medium | 23 | 7 | 4 | 5.1 |
| Low | 7 | 7 | 1 | 2.6 |
| None (info) | 271 | 8 | 27 | — |

### Top findings

| Vulnerability | CVSS | CVE | Hosts |
|---|---|---|---|
| RDP Server Man-in-the-Middle Weakness | 5.1 | CVE-2005-1794 | 7/7 |
| SMB Signing Disabled | 5.0 | — | 7/7 |
| Terminal Services Low/Medium Encryption | 4.3 | — | 7/7 |
| Terminal Services No NLA | 4.3 | — | 2/7 |
| Terminal Services Not FIPS-140 Compliant | 2.6 | — | 7/7 |

### CSV export

```python
import clickhouse_connect, csv

client = clickhouse_connect.get_client(host='localhost', port=8123,
                                       username='admin', password='...')
result = client.query('''
    SELECT scan_file, host, host_ip, os, port, protocol, svc_name,
           severity, risk_factor, plugin_id, plugin_name, plugin_family,
           cvss_base_score, arrayStringConcat(cve, '; ') AS cves,
           synopsis, solution, plugin_pub_date, plugin_mod_date
    FROM testdb.nessus_findings
    ORDER BY severity DESC, cvss_base_score DESC, host
''')

with open('nessus_findings.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(result.column_names)
    writer.writerows(result.result_rows)
```

A pre-exported copy is at `~/Downloads/nessus-samples/nessus_findings.csv`.
