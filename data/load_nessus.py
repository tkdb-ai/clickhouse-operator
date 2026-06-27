#!/usr/bin/env python3
"""
Parse one or more .nessus XML files and load findings into ClickHouse.

Usage:
    python3 load_nessus.py scan1.nessus scan2.nessus
    python3 load_nessus.py *.nessus --host localhost --port 9000 --user admin --password secret
    CH_PASSWORD=secret python3 load_nessus.py scan.nessus

The .nessus format is XML produced by Tenable Nessus. Each <ReportHost>
contains <ReportItem> elements — one per finding.

Env overrides: CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_DATABASE
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime


def detect_password():
    try:
        out = subprocess.check_output(
            ["kubectl", "get", "secret", "-A", "-o", "json"],
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out)
        for item in data["items"]:
            if item["metadata"]["name"] == "ch1-clickhouse-installation-admin":
                val = list(item["data"].values())[0]
                return base64.b64decode(val).decode()
    except Exception:
        pass
    return ""


def parse_date(s):
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%b %d %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return date(1970, 1, 1)


def parse_nessus(path):
    tree = ET.parse(path)
    root = tree.getroot()
    scan_file = os.path.basename(path)
    rows = []

    for report in root.iter("Report"):
        for host in report.iter("ReportHost"):
            host_name = host.get("name", "")
            props = {t.get("name"): t.text for t in host.iter("HostProperties/tag") or []}
            # HostProperties children are <tag name="...">
            props = {}
            for tag in host.find("HostProperties") or []:
                props[tag.get("name", "")] = tag.text or ""

            host_ip = props.get("host-ip", "")
            os_name = props.get("operating-system", "")

            for item in host.iter("ReportItem"):
                cve_list = [c.text for c in item.findall("cve") if c.text]
                rows.append({
                    "scan_file": scan_file,
                    "host": host_name,
                    "host_ip": host_ip,
                    "os": os_name,
                    "port": int(item.get("port", 0)),
                    "protocol": item.get("protocol", ""),
                    "svc_name": item.get("svc_name", ""),
                    "severity": int(item.get("severity", 0)),
                    "plugin_id": int(item.get("pluginID", 0)),
                    "plugin_name": item.get("pluginName", ""),
                    "plugin_family": item.get("pluginFamily", ""),
                    "synopsis": (item.findtext("synopsis") or "").strip(),
                    "description": (item.findtext("description") or "").strip(),
                    "solution": (item.findtext("solution") or "").strip(),
                    "risk_factor": (item.findtext("risk_factor") or "").strip(),
                    "plugin_output": (item.findtext("plugin_output") or "").strip(),
                    "cve": cve_list,
                    "cvss_base_score": float(item.findtext("cvss_base_score") or 0),
                    "cvss_vector": (item.findtext("cvss_vector") or "").strip(),
                    "plugin_pub_date": parse_date(item.findtext("plugin_publication_date") or ""),
                    "plugin_mod_date": parse_date(item.findtext("plugin_modification_date") or ""),
                })
    return rows


def row_to_tsv(r):
    cve_str = "['" + "','".join(r["cve"]) + "']" if r["cve"] else "[]"
    return "\t".join([
        r["scan_file"], r["host"], r["host_ip"], r["os"],
        str(r["port"]), r["protocol"], r["svc_name"],
        str(r["severity"]), str(r["plugin_id"]),
        r["plugin_name"], r["plugin_family"],
        r["synopsis"].replace("\t", " ").replace("\n", " "),
        r["description"].replace("\t", " ").replace("\n", " "),
        r["solution"].replace("\t", " ").replace("\n", " "),
        r["risk_factor"],
        r["plugin_output"].replace("\t", " ").replace("\n", " "),
        cve_str,
        str(r["cvss_base_score"]),
        r["cvss_vector"],
        str(r["plugin_pub_date"]),
        str(r["plugin_mod_date"]),
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help=".nessus XML files to load")
    parser.add_argument("--host", default=os.environ.get("CH_HOST", "localhost"))
    parser.add_argument("--port", default=os.environ.get("CH_PORT", "9000"))
    parser.add_argument("--user", default=os.environ.get("CH_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("CH_PASSWORD") or detect_password())
    parser.add_argument("--database", default=os.environ.get("CH_DATABASE", "testdb"))
    parser.add_argument("--truncate", action="store_true", help="truncate table before loading")
    args = parser.parse_args()

    if not args.password:
        print("error: --password not set and could not be detected from kubectl", file=sys.stderr)
        sys.exit(1)

    ch_cmd = [
        "clickhouse", "client",
        "--host", args.host,
        "--port", args.port,
        "--user", args.user,
        "--password", args.password,
        "--database", args.database,
    ]

    def ch(query):
        subprocess.run(ch_cmd + ["--query", query], check=True)

    print("==> Creating database and table if not exists")
    ch(f"CREATE DATABASE IF NOT EXISTS {args.database}")
    ch("""
        CREATE TABLE IF NOT EXISTS nessus_findings (
            scan_file       String,
            host            String,
            host_ip         String,
            os              String,
            port            UInt16,
            protocol        String,
            svc_name        String,
            severity        UInt8,
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
        ) ENGINE = MergeTree
          ORDER BY (severity, plugin_id, host)
    """)

    if args.truncate:
        print("==> Truncating nessus_findings")
        ch("TRUNCATE TABLE nessus_findings")

    for path in args.files:
        print(f"==> Parsing {path}")
        rows = parse_nessus(path)
        print(f"    {len(rows)} findings found")
        if not rows:
            continue

        tsv_data = "\n".join(row_to_tsv(r) for r in rows).encode()
        insert_cmd = ch_cmd + [
            "--query",
            "INSERT INTO nessus_findings FORMAT TSV",
        ]
        proc = subprocess.run(insert_cmd, input=tsv_data, check=True)
        print(f"    loaded {len(rows)} rows from {path}")

    result = subprocess.check_output(ch_cmd + ["--query", "SELECT count() FROM nessus_findings"])
    print(f"==> Total rows in nessus_findings: {result.decode().strip()}")


if __name__ == "__main__":
    main()
