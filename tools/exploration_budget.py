#!/usr/bin/env python3
"""Report reproducible firmware sizes and exploration timing budgets.

Run from the repository root with:
    uv run python -m tools.exploration_budget > docs/exploration_budget.json

Cycle allowances are arithmetic budgets, not measured firmware performance.
Protocol rates are experiment targets, not verified capabilities.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.assembler import PROGRAM_WORDS, assemble

ROOT = Path(__file__).resolve().parents[1]
CLOCK_HZ = 50_000_000


def report() -> dict:
    firmware = {}
    for path in sorted((ROOT / "firmware").glob("*.asm")):
        words = assemble(path.read_text())
        firmware[str(path.relative_to(ROOT))] = {
            "words": len(words),
            "free_words": PROGRAM_WORDS - len(words),
            "loader_tokens": 3 * len(words),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    rates = {
        "uart": (115_200, "serial bit"),
        "spi": (100_000, "SCLK period"),
        "i2c": (100_000, "unstretched SCL period"),
        "jtag": (100_000, "TCK period"),
        "swd": (100_000, "SWCLK period"),
        "ps2": (12_500, "device clock period; test target"),
        "can": (125_000, "serial bit"),
        "usb_ls": (1_500_000, "serial bit"),
        "ethernet_sni": (10_000_000, "SNI serial bit"),
    }
    sources = [
        "src/protocol_core.v",
        "src/runtime_bridge.v",
        "src/runtime_store.v",
        "tools/assembler.py",
        "tools/runtime.py",
    ]
    return {
        "schema": 1,
        "basis": "Source inspection and assembly; no new protocol simulations or physical builds",
        "clock_hz": CLOCK_HZ,
        "program_capacity_words": PROGRAM_WORDS,
        "firmware": firmware,
        "target_budgets": {
            name: {
                "rate_hz": rate,
                "unit": unit,
                "core_cycles_per_unit": CLOCK_HZ / rate,
            }
            for name, (rate, unit) in rates.items()
        },
        "host_transport": {
            "read8_tokens": 5,
            "write8_tokens": 6,
            "input64_write_tokens": 64 * 6,
            "submission_and_commit_write_tokens": (16 + 1) * 6,
            "output64_data_metadata_pop_tokens": 64 * (5 + 5 + 6),
            "terminal_event_read_tokens": 16 * 5,
            "note": "Excludes arguments, flush, status/occupancy polling and all board/handshake latency; not a throughput measurement",
        },
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sources
        },
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
