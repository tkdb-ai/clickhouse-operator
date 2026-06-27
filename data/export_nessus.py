#!/usr/bin/env python3
"""
Export nessus_findings from ClickHouse back to .nessus XML files.

Usage:
    python3 export_nessus.py                   # exports all scan files to data/nessus/
    python3 export_nessus.py --out /tmp/scans
"""

import argparse
import json
import os
import subprocess
import sys
import base64
import xml.etree.ElementTree as ET
from collections import defaultdict


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


def ch_query(cmd_base, query):
    result = subprocess.check_output(cmd_base + ["--query", query, "--output-format", "JSONEachRow"])
    return [json.loads(line) for line in result.splitlines() if line.strip()]


def build_nessus_xml(scan_file, rows):
    root = ET.Element("NessusClientData_v2")
    report = ET.SubElement(root, "Report", name=scan_file.replace(".nessus", "").replace(".xml", ""))

    # Group rows by host
    by_host = defaultdict(list)
    for r in rows:
        by_host[(r["host"], r["host_ip"], r["os"])].append(r)

    for (host, host_ip, os_name), findings in by_host.items():
        report_host = ET.SubElement(report, "ReportHost", name=host)
        host_props = ET.SubElement(report_host, "HostProperties")
        for name, val in [("host-ip", host_ip), ("operating-system", os_name)]:
            if val:
                tag = ET.SubElement(host_props, "tag", name=name)
                tag.text = val

        for f in findings:
            item = ET.SubElement(
                report_host, "ReportItem",
                port=str(f["port"]),
                svc_name=f["svc_name"],
                protocol=f["protocol"],
                severity=str(f["severity"]),
                pluginID=str(f["plugin_id"]),
                pluginName=f["plugin_name"],
                pluginFamily=f["plugin_family"],
            )
            for tag, val in [
                ("synopsis", f["synopsis"]),
                ("description", f["description"]),
                ("solution", f["solution"]),
                ("risk_factor", f["risk_factor"]),
                ("plugin_output", f["plugin_output"]),
                ("cvss_base_score", str(f["cvss_base_score"]) if f["cvss_base_score"] else ""),
                ("cvss_vector", f["cvss_vector"]),
                ("plugin_publication_date", f["plugin_pub_date"]),
                ("plugin_modification_date", f["plugin_mod_date"]),
            ]:
                if val:
                    el = ET.SubElement(item, tag)
                    el.text = val

            for cve in f.get("cve", []):
                el = ET.SubElement(item, "cve")
                el.text = cve

    from xml.dom import minidom
    raw = ET.tostring(root, encoding="unicode")
    return minidom.parseString(raw).toprettyxml(indent="  ")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.join(script_dir, "nessus")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=os.environ.get("CH_HOST", "localhost"))
    parser.add_argument("--port", default=os.environ.get("CH_PORT", "9000"))
    parser.add_argument("--user", default=os.environ.get("CH_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("CH_PASSWORD") or detect_password())
    parser.add_argument("--database", default=os.environ.get("CH_DATABASE", "testdb"))
    parser.add_argument("--out", default=default_out, help="output directory")
    args = parser.parse_args()

    if not args.password:
        print("error: --password not set and could not be detected from kubectl", file=sys.stderr)
        sys.exit(1)

    ch_cmd = [
        "clickhouse", "client",
        "--host", args.host, "--port", args.port,
        "--user", args.user, "--password", args.password,
        "--database", args.database,
    ]

    os.makedirs(args.out, exist_ok=True)

    scan_files = [
        r["scan_file"]
        for r in ch_query(ch_cmd, "SELECT DISTINCT scan_file FROM nessus_findings ORDER BY scan_file")
    ]
    print(f"==> Found {len(scan_files)} scan file(s): {', '.join(scan_files)}")

    for scan_file in scan_files:
        print(f"==> Exporting {scan_file}")
        rows = ch_query(ch_cmd, f"SELECT * FROM nessus_findings WHERE scan_file = '{scan_file}'")
        xml_str = build_nessus_xml(scan_file, rows)

        # Always save as .nessus regardless of original extension
        out_name = scan_file if scan_file.endswith(".nessus") else os.path.splitext(scan_file)[0] + ".nessus"
        out_path = os.path.join(args.out, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        print(f"    wrote {len(rows)} findings -> {out_path}")

    print("==> Done")


if __name__ == "__main__":
    main()
