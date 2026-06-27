#!/usr/bin/env python3
"""
Generate realistic sample .nessus XML files for testing.

Produces two files in data/nessus/:
  - sample_windows_network.nessus  (Windows hosts, mixed severity)
  - sample_linux_web.nessus        (Linux/web hosts, mixed severity)

Usage:
    python3 data/generate_nessus_samples.py
"""

import os
from xml.dom import minidom
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "nessus")

# ---------------------------------------------------------------------------
# Plugin library — realistic Nessus plugins with CVEs across all severities
# ---------------------------------------------------------------------------

PLUGINS = [
    # Critical (severity=4)
    dict(
        plugin_id=93561, plugin_name="OpenSSL RCE (CVE-2016-6309)", plugin_family="Web Servers",
        severity=4, risk_factor="Critical", cvss=9.8,
        cvss_vector="CVSS2#AV:N/AC:L/Au:N/C:C/I:C/A:C",
        cve=["CVE-2016-6309"],
        synopsis="The remote service is affected by a critical remote code execution vulnerability.",
        description="The version of OpenSSL installed on the remote host is affected by a use-after-free memory error. An unauthenticated, remote attacker can exploit this to execute arbitrary code.",
        solution="Upgrade to OpenSSL 1.1.0a or later.",
        ports=[("443", "tcp", "https"), ("8443", "tcp", "https")],
        pub_date="2016/09/26", mod_date="2021/01/19",
        output="OpenSSL version detected: 1.0.2h\nPath: /usr/lib/ssl",
    ),
    dict(
        plugin_id=97737, plugin_name="MS17-010: EternalBlue SMB RCE (WannaCry)", plugin_family="Windows",
        severity=4, risk_factor="Critical", cvss=9.3,
        cvss_vector="CVSS2#AV:N/AC:M/Au:N/C:C/I:C/A:C",
        cve=["CVE-2017-0143", "CVE-2017-0144", "CVE-2017-0145"],
        synopsis="The remote Windows host is affected by a critical remote code execution vulnerability.",
        description="The remote Windows host is missing a security update and is affected by the EternalBlue SMB vulnerability used by WannaCry and NotPetya ransomware.",
        solution="Apply Microsoft Security Bulletin MS17-010.",
        ports=[("445", "tcp", "microsoft-ds")],
        pub_date="2017/03/14", mod_date="2022/06/09",
        output="Missing patch: KB4012212\nSMB dialect: SMBv1 enabled",
    ),
    dict(
        plugin_id=70658, plugin_name="MS14-066: RCE in SChannel (POODLE/SSL)", plugin_family="Windows",
        severity=4, risk_factor="Critical", cvss=10.0,
        cvss_vector="CVSS2#AV:N/AC:L/Au:N/C:C/I:C/A:C",
        cve=["CVE-2014-6321"],
        synopsis="The remote Windows host is affected by a critical vulnerability in Microsoft SChannel.",
        description="A remote code execution vulnerability exists in the Microsoft Secure Channel (Schannel) security package due to improper processing of specially crafted packets.",
        solution="Microsoft has released a set of patches for Windows 2008, 2012 R2.",
        ports=[("443", "tcp", "https")],
        pub_date="2014/11/11", mod_date="2019/08/13",
        output="Vulnerable SChannel version detected.\nOS: Windows Server 2008 R2",
    ),
    dict(
        plugin_id=33850, plugin_name="Unsupported Unix Operating System", plugin_family="General",
        severity=4, risk_factor="Critical", cvss=10.0,
        cvss_vector="CVSS2#AV:N/AC:L/Au:N/C:C/I:C/A:C",
        cve=[],
        synopsis="The remote host is running an obsolete operating system.",
        description="The remote host is running an operating system that is no longer supported by its vendor. Lack of support implies that no new security patches will be released for it.",
        solution="Upgrade to a supported operating system.",
        ports=[("0", "tcp", "general")],
        pub_date="2008/08/08", mod_date="2023/05/10",
        output="OS: Ubuntu 14.04 LTS\nEnd of life: April 2019",
    ),

    # High (severity=3)
    dict(
        plugin_id=51192, plugin_name="SSL Certificate Cannot Be Trusted", plugin_family="General",
        severity=3, risk_factor="High", cvss=6.4,
        cvss_vector="CVSS2#AV:N/AC:L/Au:N/C:P/I:P/A:N",
        cve=[],
        synopsis="The SSL certificate for this service cannot be trusted.",
        description="The server's X.509 certificate does not have a signature from a known public certificate authority. This situation can occur in three different ways: the certificate is self-signed, signed by an unknown CA, or signed by an untrusted CA.",
        solution="Purchase or generate a proper SSL certificate for the service.",
        ports=[("443", "tcp", "https"), ("8443", "tcp", "https")],
        pub_date="2010/12/15", mod_date="2021/02/03",
        output="The certificate is self-signed.\nSubject: CN=localhost",
    ),
    dict(
        plugin_id=57582, plugin_name="SSL Self-Signed Certificate", plugin_family="General",
        severity=3, risk_factor="High", cvss=6.4,
        cvss_vector="CVSS2#AV:N/AC:L/Au:N/C:P/I:P/A:N",
        cve=[],
        synopsis="The SSL certificate chain for this service ends in an unrecognized self-signed certificate.",
        description="The X.509 certificate chain for this service is not signed by a recognized certificate authority.",
        solution="Replace the SSL certificate with one signed by a recognized CA.",
        ports=[("443", "tcp", "https")],
        pub_date="2012/01/17", mod_date="2021/02/03",
        output="Certificate details:\n  Subject: CN=web01.internal\n  Issuer: CN=web01.internal\n  Expiry: 2024-01-01",
    ),
    dict(
        plugin_id=35291, plugin_name="SSL Certificate Expiry", plugin_family="General",
        severity=3, risk_factor="High", cvss=0.0,
        cvss_vector="",
        cve=[],
        synopsis="The remote server's SSL certificate has already expired.",
        description="This plugin checks the expiry of SSL certificates on the remote host. An expired certificate may indicate a misconfiguration or an abandoned service.",
        solution="Renew the SSL certificate.",
        ports=[("443", "tcp", "https")],
        pub_date="2009/01/06", mod_date="2021/09/23",
        output="The SSL certificate has already expired:\n  Not After : Jan 01 00:00:00 2023 GMT",
    ),
    dict(
        plugin_id=90510, plugin_name="MS16-047: SAM/LSAD Downgrade Vulnerability (Badlock)", plugin_family="Windows",
        severity=3, risk_factor="High", cvss=6.8,
        cvss_vector="CVSS2#AV:N/AC:M/Au:N/C:P/I:P/A:P",
        cve=["CVE-2016-0128"],
        synopsis="The remote host is affected by a man-in-the-middle vulnerability.",
        description="The remote Windows host is missing a security update and is therefore affected by a man-in-the-middle (MitM) vulnerability, known as 'Badlock', in the SAM and LSAD protocols.",
        solution="Apply Microsoft Security Bulletin MS16-047.",
        ports=[("445", "tcp", "microsoft-ds"), ("139", "tcp", "netbios-ssn")],
        pub_date="2016/04/12", mod_date="2019/11/25",
        output="Missing patch: KB3148538",
    ),
    dict(
        plugin_id=104743, plugin_name="TLS Version 1.0 Deprecated", plugin_family="General",
        severity=3, risk_factor="High", cvss=7.4,
        cvss_vector="CVSS2#AV:N/AC:M/Au:N/C:C/I:N/A:N",
        cve=["CVE-2011-3389"],
        synopsis="The remote service encrypts traffic using an older version of TLS.",
        description="The remote service accepts connections encrypted using TLS 1.0. TLS 1.0 has a number of cryptographic design flaws and has been deprecated by RFC 8996.",
        solution="Enable support for TLS 1.2 and 1.3, and disable TLS 1.0.",
        ports=[("443", "tcp", "https"), ("3389", "tcp", "msrdp")],
        pub_date="2017/11/22", mod_date="2023/04/11",
        output="TLS 1.0 is enabled on port 443.\nTLS 1.0 is enabled on port 3389.",
    ),

    # Medium (severity=2)
    dict(
        plugin_id=10881, plugin_name="SSH Protocol Version 1 Enabled", plugin_family="Misc.",
        severity=2, risk_factor="Medium", cvss=5.0,
        cvss_vector="CVSS2#AV:N/AC:L/Au:N/C:P/I:N/A:N",
        cve=[],
        synopsis="The remote host supports SSH protocol version 1.",
        description="The remote SSH daemon supports SSH protocol version 1, which is not recommended. SSH protocol version 1 has cryptographic weaknesses.",
        solution="Disable SSH v1 in sshd_config and restart the SSH service.",
        ports=[("22", "tcp", "ssh")],
        pub_date="2002/03/06", mod_date="2019/10/04",
        output="The remote SSH server supports SSHv1.\nSSHv1 session key: diffie-hellman-group1-sha1",
    ),
    dict(
        plugin_id=65821, plugin_name="SSL RC4 Cipher Suites Supported (Bar Mitzvah)", plugin_family="General",
        severity=2, risk_factor="Medium", cvss=4.3,
        cvss_vector="CVSS2#AV:N/AC:M/Au:N/C:P/I:N/A:N",
        cve=["CVE-2013-2566", "CVE-2015-2808"],
        synopsis="The remote service supports the use of the RC4 cipher.",
        description="The remote host supports the use of RC4 in one or more cipher suites. The RC4 cipher is flawed in its generation of a pseudo-random stream of bytes so that a wide variety of small biases are introduced.",
        solution="Reconfigure the affected application to avoid use of RC4 ciphers.",
        ports=[("443", "tcp", "https")],
        pub_date="2013/04/05", mod_date="2021/01/19",
        output="RC4 cipher suites supported:\n  TLS_RSA_WITH_RC4_128_MD5\n  TLS_RSA_WITH_RC4_128_SHA",
    ),
    dict(
        plugin_id=42873, plugin_name="SSL Medium Strength Cipher Suites Supported (SWEET32)", plugin_family="General",
        severity=2, risk_factor="Medium", cvss=4.3,
        cvss_vector="CVSS2#AV:N/AC:M/Au:N/C:P/I:N/A:N",
        cve=["CVE-2016-2183"],
        synopsis="The remote service supports the use of medium strength SSL cipher suites.",
        description="The remote host supports the use of SSL cipher suites that offer medium strength encryption. SWEET32 exploits the birthday attack on 64-bit block ciphers (3DES, Blowfish).",
        solution="Reconfigure the affected application to avoid use of medium strength cipher suites.",
        ports=[("443", "tcp", "https"), ("3389", "tcp", "msrdp")],
        pub_date="2009/11/23", mod_date="2021/02/03",
        output="Medium strength cipher suites supported:\n  TLS_RSA_WITH_3DES_EDE_CBC_SHA",
    ),
    dict(
        plugin_id=10107, plugin_name="HTTP Server Type and Version", plugin_family="Web Servers",
        severity=0, risk_factor="None", cvss=0.0,
        cvss_vector="",
        cve=[],
        synopsis="A web server is running on the remote host.",
        description="This plugin attempts to determine the type and the version of the remote web server.",
        solution="n/a",
        ports=[("80", "tcp", "www"), ("8080", "tcp", "http-proxy")],
        pub_date="2007/01/30", mod_date="2020/01/20",
        output="The remote web server type is :\n  Apache/2.4.41 (Ubuntu)",
    ),

    # Low (severity=1)
    dict(
        plugin_id=10263, plugin_name="SMTP Server Detection", plugin_family="Service detection",
        severity=1, risk_factor="Low", cvss=0.0,
        cvss_vector="",
        cve=[],
        synopsis="An SMTP server is listening on the remote port.",
        description="The remote host is running a mail server (SMTP). Attackers may use information leaked by SMTP servers to target the system.",
        solution="Restrict access to the SMTP port or configure the server to not reveal version information.",
        ports=[("25", "tcp", "smtp")],
        pub_date="1999/10/12", mod_date="2020/06/12",
        output="Remote SMTP server banner:\n  220 mail.example.com ESMTP Postfix (Ubuntu)",
    ),
    dict(
        plugin_id=11219, plugin_name="Nessus SYN scanner", plugin_family="Port scanners",
        severity=0, risk_factor="None", cvss=0.0,
        cvss_vector="",
        cve=[],
        synopsis="It is possible to determine which TCP ports are open.",
        description="This plugin is a SYN 'half-open' port scanner. It shall be reasonably quick even against a firewalled target.",
        solution="Protect your target with an IP filter.",
        ports=[("22", "tcp", "ssh"), ("80", "tcp", "www"), ("443", "tcp", "https")],
        pub_date="2009/02/04", mod_date="2023/02/17",
        output="Port 22/tcp was found to be open\nPort 80/tcp was found to be open\nPort 443/tcp was found to be open",
    ),
]

# ---------------------------------------------------------------------------
# Host definitions
# ---------------------------------------------------------------------------

WINDOWS_HOSTS = [
    dict(name="windc01",   ip="10.10.0.10", os="Microsoft Windows Server 2019 Standard",
         plugins=[97737, 90510, 10881, 42873, 51192, 35291, 104743, 11219]),
    dict(name="windc02",   ip="10.10.0.11", os="Microsoft Windows Server 2016 Standard",
         plugins=[90510, 42873, 51192, 104743, 11219]),
    dict(name="winapp01",  ip="10.10.1.10", os="Microsoft Windows Server 2019 Standard",
         plugins=[70658, 51192, 57582, 42873, 65821, 104743, 10107, 11219]),
    dict(name="winapp02",  ip="10.10.1.11", os="Microsoft Windows Server 2019 Standard",
         plugins=[70658, 51192, 57582, 42873, 104743, 10107, 11219]),
    dict(name="winapp03",  ip="10.10.1.12", os="Microsoft Windows Server 2016 Standard",
         plugins=[51192, 42873, 104743, 10107, 11219]),
    dict(name="winfile01", ip="10.10.2.10", os="Microsoft Windows Server 2019 Standard",
         plugins=[97737, 42873, 104743, 11219]),
]

LINUX_HOSTS = [
    dict(name="webprod01", ip="192.168.10.10", os="Ubuntu Linux 14.04 LTS",
         plugins=[33850, 93561, 51192, 57582, 65821, 42873, 10881, 10107, 10263, 11219]),
    dict(name="webprod02", ip="192.168.10.11", os="Ubuntu Linux 14.04 LTS",
         plugins=[33850, 93561, 51192, 65821, 42873, 10881, 10107, 11219]),
    dict(name="webdev01",  ip="192.168.10.20", os="Ubuntu Linux 20.04 LTS",
         plugins=[51192, 57582, 42873, 10107, 10263, 11219]),
    dict(name="dbprod01",  ip="192.168.20.10", os="CentOS Linux 7",
         plugins=[51192, 10881, 42873, 104743, 11219]),
    dict(name="dbprod02",  ip="192.168.20.11", os="CentOS Linux 7",
         plugins=[51192, 10881, 42873, 104743, 11219]),
    dict(name="mailsrv01", ip="192.168.30.10", os="Debian GNU/Linux 9",
         plugins=[51192, 57582, 10881, 10263, 42873, 11219]),
]

# ---------------------------------------------------------------------------
# Build XML
# ---------------------------------------------------------------------------

PLUGIN_MAP = {p["plugin_id"]: p for p in PLUGINS}


def add_text(parent, tag, text):
    el = ET.SubElement(parent, tag)
    el.text = text
    return el


def build_report(scan_name, hosts):
    root = ET.Element("NessusClientData_v2")
    report = ET.SubElement(root, "Report", name=scan_name)

    for host in hosts:
        rh = ET.SubElement(report, "ReportHost", name=host["name"])
        hp = ET.SubElement(rh, "HostProperties")
        for name, val in [("host-ip", host["ip"]), ("operating-system", host["os"])]:
            tag = ET.SubElement(hp, "tag", name=name)
            tag.text = val

        for pid in host["plugins"]:
            p = PLUGIN_MAP[pid]
            for port, proto, svc in p["ports"]:
                item = ET.SubElement(
                    rh, "ReportItem",
                    port=port, svc_name=svc, protocol=proto,
                    severity=str(p["severity"]),
                    pluginID=str(p["plugin_id"]),
                    pluginName=p["plugin_name"],
                    pluginFamily=p["plugin_family"],
                )
                add_text(item, "synopsis", p["synopsis"])
                add_text(item, "description", p["description"])
                add_text(item, "solution", p["solution"])
                add_text(item, "risk_factor", p["risk_factor"])
                if p["output"]:
                    add_text(item, "plugin_output", p["output"])
                if p["cvss"]:
                    add_text(item, "cvss_base_score", str(p["cvss"]))
                if p["cvss_vector"]:
                    add_text(item, "cvss_vector", p["cvss_vector"])
                for cve in p["cve"]:
                    add_text(item, "cve", cve)
                add_text(item, "plugin_publication_date", p["pub_date"])
                add_text(item, "plugin_modification_date", p["mod_date"])

    return minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")


def main():
    from xml.dom import minidom  # noqa: F401 — used in build_report
    os.makedirs(OUT_DIR, exist_ok=True)

    scans = [
        ("sample_windows_network.nessus", "Windows Network Scan", WINDOWS_HOSTS),
        ("sample_linux_web.nessus",       "Linux Web Infrastructure Scan", LINUX_HOSTS),
    ]

    for filename, scan_name, hosts in scans:
        xml = build_report(scan_name, hosts)
        path = os.path.join(OUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        total = sum(len(h["plugins"]) for h in hosts)
        print(f"wrote {path}  ({len(hosts)} hosts, {total} findings)")


if __name__ == "__main__":
    main()
