#!/usr/bin/env python3
"""Diff docs/netlist.json against the KiCad schematic, net by net.

docs/netlist.json exists to be checked, not read. This is the check.

    kicad-cli sch export netlist --format kicadxml --output build/netlist.xml pcb/remote/remote.kicad_sch
    python pcb/check_netlist.py build/netlist.xml

Exits non-zero if the drawn schematic and the spec disagree. It has already
caught a board-killing defect once: the XIAO powered through its 5V pin with
B+/B- absent, which silently removes battery charging.

The schematic models the XIAO's pads as three connectors (J3/J4/J6) because the
module has no single symbol, so connector pins are mapped back to the U1.* names
the spec uses before comparing.
"""
import json
import os
import sys

# stdlib ElementTree is fine here: the only input is a netlist this repo
# generates itself with kicad-cli. Swap in defusedxml if that ever stops
# being true.
import xml.etree.ElementTree as ET
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, os.pardir, "docs", "netlist.json")

# Connector pin -> the canonical name used in docs/netlist.json.
PINMAP = {
    "J3":  {"1": "U1.D0", "2": "U1.D1", "3": "U1.D2", "4": "U1.D3",
            "5": "U1.D4", "6": "U1.D5", "7": "U1.D6"},
    "J4":  {"1": "U1.D7", "2": "U1.D8", "3": "U1.D9", "4": "U1.D10",
            "5": "U1.3V3", "6": "U1.GND", "7": "U1.5V"},
    "J6":  {"1": "U1.B+", "2": "U1.B-"},
    "U2":  {"1": "U2.VDD", "2": "U2.GND", "3": "U2.SD",
            "4": "U2.L/R", "5": "U2.WS", "6": "U2.SCK"},
    "U3":  {"1": "U3.VIN", "2": "U3.GND", "3": "U3.SD", "4": "U3.GAIN",
            "5": "U3.BCLK", "6": "U3.LRC", "7": "U3.DIN"},
    # Switch:SW_SPDT pin 2 (B) is the wiper. The battery goes on the common,
    # the switched rail on a throw -- the reverse still works as an on/off
    # switch, which is why it survived review the first time.
    "SW2": {"1": "SW2.OUT", "2": "SW2.COMMON", "3": "SW2.NC"},
    # SW_Push pin 1 is the grounded side; the spec calls the signal side .1
    "SW1": {"1": "SW1.2", "2": "SW1.1"},
}
# Polarised electrolytics are written +/- in the spec, not 1/2.
POLARISED = {"C1", "C3", "C5"}
# The schematic uses KiCad's rail names; the spec uses its own.
NETNAME = {"VBAT_IN": "BAT+", "+3V3": "3V3"}


def canonical(ref, pin):
    """Map one schematic pin to the name docs/netlist.json uses, or None to skip."""
    if ref.startswith("#"):          # power symbols and PWR_FLAGs
        return None
    if ref in PINMAP:
        return PINMAP[ref][pin]
    if ref in POLARISED:
        return "%s.%s" % (ref, "+" if pin == "1" else "-")
    if ref.startswith("TP"):         # test points have one pin; the ref is enough
        return ref
    return "%s.%s" % (ref, pin)


def read_schematic(xml_path):
    """-> (nets: {name: {terminal}}, no_connect: {terminal})"""
    nets, no_connect = defaultdict(set), set()
    for net in ET.parse(xml_path).getroot().findall("./nets/net"):
        name = (net.get("name") or "").lstrip("/")
        terminals = set()
        for node in net.findall("node"):
            t = canonical(node.get("ref"), node.get("pin"))
            if t:
                terminals.add(t)
        # KiCad gives every no-connect pin its own pseudo-net. That is the point:
        # it proves the pins are isolated rather than sharing a net.
        if name.startswith("unconnected-"):
            no_connect |= terminals
        else:
            nets[NETNAME.get(name, name)] |= terminals
    return nets, no_connect


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    spec = json.load(open(SPEC, encoding="utf-8"))
    nets, no_connect = read_schematic(sys.argv[1])
    problems = []

    print("%-16s %5s %5s  %s" % ("NET", "SPEC", "SCH", "RESULT"))
    print("-" * 60)
    for name in sorted(set(spec["nets"]) | set(nets)):
        want = set(spec["nets"].get(name, {}).get("members", []))
        have = nets.get(name, set())
        missing, extra = want - have, have - want
        if missing or extra or not want:
            problems.append(name)
        print("%-16s %5d %5d  %s"
              % (name, len(want), len(have), "ok" if not (missing or extra or not want) else "DIFFERS"))
        for label, items in (("missing from schematic", missing), ("not in spec", extra)):
            if items:
                print("     %-22s : %s" % (label, ", ".join(sorted(items))))

    print("-" * 60)
    want_nc = set(k for k in spec.get("no_connect", {}) if not k.startswith("_"))
    missing_nc, extra_nc = want_nc - no_connect, no_connect - want_nc
    print("no-connect       %5d %5d  %s"
          % (len(want_nc), len(no_connect), "ok" if not (missing_nc or extra_nc) else "DIFFERS"))
    if missing_nc:
        print("     not flagged in schematic : %s" % ", ".join(sorted(missing_nc)))
        print("     (a pin missing its own flag may be sharing a net -- D6/D7 are UART TX/RX)")
    if extra_nc:
        print("     unexpectedly unconnected : %s" % ", ".join(sorted(extra_nc)))
    if missing_nc or extra_nc:
        problems.append("no_connect")

    total = sum(len(v["members"]) for v in spec["nets"].values())
    print("\n%d nets, %d connections, %d no-connect pins"
          % (len(spec["nets"]), total, len(want_nc)))
    if problems:
        print("FAIL: %s" % ", ".join(problems))
        return 1
    print("PASS: schematic matches docs/netlist.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
