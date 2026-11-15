#!/usr/bin/env python3
"""
capdiff.py - pull host->mouse HID packets out of USBPcap/Wireshark captures and diff them.

Use it to decode settings OpenRGB doesn't cover (DPI, polling rate, lift-off, buttons):
  1. In Wireshark + USBPcap, capture while changing ONE setting in MasterPlus+
     (e.g. dpi_800.pcapng, then dpi_1600.pcapng).
  2. python capdiff.py dpi_800.pcapng dpi_1600.pcapng
  3. Packets that differ are printed with the changed byte positions marked.

Needs `tshark` on PATH (ships with Wireshark).
"""

import argparse
import shutil
import subprocess
import sys

VID_FILTER = "usb.idVendor == 0x2516"   # informational; captures usually hold one device


def outgoing_packets(path, min_len=8):
    """Return unique host->device data payloads (as bytes), in capture order."""
    if not shutil.which("tshark"):
        sys.exit("tshark not found. Install Wireshark and add it to PATH.")
    cmd = ["tshark", "-r", path,
           "-Y", 'usb.src == "host" && (usbhid.data || usb.capdata || usb.data_fragment)',
           "-T", "fields", "-e", "usbhid.data", "-e", "usb.capdata", "-e", "usb.data_fragment"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    seen, pkts = set(), []
    for line in out.splitlines():
        field = next((f for f in line.split("\t") if f), "")
        hexstr = field.replace(":", "").strip()
        if not hexstr:
            continue
        data = bytes.fromhex(hexstr)
        if len(data) < min_len or data in seen:
            continue
        seen.add(data)
        pkts.append(data)
    return pkts


def show(data, n=24):
    return " ".join(f"{b:02x}" for b in data[:n])


def key(p):
    """Group packets by their first 3 bytes (command + sub-command)."""
    return p[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+", help="one capture to dump, or two to diff")
    ap.add_argument("-n", type=int, default=24, help="bytes to show per packet")
    a = ap.parse_args()

    if len(a.captures) == 1:
        for i, p in enumerate(outgoing_packets(a.captures[0])):
            print(f"{i:3}: {show(p, a.n)}")
        return

    A, B = (outgoing_packets(c) for c in a.captures[:2])
    by_key_a = {}
    for p in A:
        by_key_a.setdefault(key(p), []).append(p)

    print(f"A = {a.captures[0]} ({len(A)} unique out packets)")
    print(f"B = {a.captures[1]} ({len(B)} unique out packets)\n")
    setA = set(A)
    for p in B:
        if p in setA:
            continue
        twins = by_key_a.get(key(p))
        if not twins:
            print(f"only in B:  {show(p, a.n)}")
            continue
        q = twins[0]
        diffs = [i for i in range(min(len(p), len(q), a.n)) if p[i] != q[i]]
        print(f"A:          {show(q, a.n)}")
        print(f"B:          {show(p, a.n)}")
        print("            " + "".join("^^ " if i in diffs else "   " for i in range(min(a.n, len(p)))))
        print(f"            changed byte offsets: {diffs}\n")
    for p in A:
        if p not in set(B) and key(p) not in {key(x) for x in B}:
            print(f"only in A:  {show(p, a.n)}")


if __name__ == "__main__":
    main()
