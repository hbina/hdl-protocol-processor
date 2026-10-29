"""Differential simulation of a fixed IPv4 header checksum circuit."""

import argparse
import json
from pathlib import Path
import random
import subprocess

from examples.combinational.ipv4_checksum import component
from .check_simulation import ROOT, run_case


def reference(data: bytes) -> int:
    # Carry is folded after each network-order word, unlike the hardware tree.
    total = 0
    for i in range(0, len(data), 2):
        total += data[i] * 256 + data[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return 0xFFFF ^ total


def expected(header: int) -> dict[str, int]:
    data = header.to_bytes(20, "big")
    cleared = data[:10] + b"\x00\x00" + data[12:]
    return {"checksum": reference(cleared), "valid": int(reference(data) == 0)}


def cases() -> list[tuple[dict[str, int], dict[str, int]]]:
    headers = [0, (1 << 160) - 1]
    headers += [1 << bit for bit in range(160)]
    headers += [((1 << 160) - 1) ^ (1 << bit) for bit in range(160)]
    # Known IPv4 header, checksum 0xb861, and the RFC 1071 numeric example 0x220d.
    headers += [int("450000730000400040110000c0a80001c0a800c7", 16)]
    headers += [int.from_bytes(bytes.fromhex("0001f203f4f5f6f7") + bytes(12), "big")]
    rng = random.Random(20261029)
    headers += [rng.getrandbits(160) for _ in range(512)]
    vectors: list[tuple[dict[str, int], dict[str, int]]] = []
    for header in headers:
        vectors.append(({"header": header}, expected(header)))
        cleared = header & ~(0xFFFF << 64)
        checksum = expected(header)["checksum"]
        corrected = cleared | (checksum << 64)
        vectors.append(({"header": corrected}, {"checksum": checksum, "valid": 1}))
        # Every single-bit flip of a valid header must be detected.
        bit = rng.randrange(160)
        damaged = corrected ^ (1 << bit)
        vectors.append(({"header": damaged}, expected(damaged)))
        assert expected(damaged)["valid"] == 0
    return vectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", choices=("icarus", "verilator"), required=True)
    parser.add_argument("--executable")
    args = parser.parse_args()
    executable = args.executable or (
        "iverilog" if args.sim == "icarus" else "verilator"
    )
    if "/" in executable:
        executable = str(Path(executable).resolve())
    output = ROOT / "build/checksum"
    result = run_case(args.sim, executable, component, cases(), output)
    flag = "-V" if args.sim == "icarus" else "--version"
    version = subprocess.run(
        [executable, flag], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]
    (output / args.sim / "results.json").write_text(
        json.dumps({"tool": version, "case": result}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
