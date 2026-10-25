from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_bench(tmp_path, top, parameters=()):
    image = tmp_path / "unit.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            top,
            *parameters,
            "-o",
            str(image),
            str(ROOT / "src/runtime_fifo.v"),
            str(ROOT / "src/runtime_store.v"),
            str(ROOT / "test/runtime_units_tb.v"),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(["vvp", str(image)], check=True, capture_output=True, timeout=30)


def test_runtime_storage_boundaries(tmp_path):
    run_bench(tmp_path, "runtime_units_tb")


@pytest.mark.parametrize("depth", [1, 3, 4, 64])
def test_fifo_simultaneous_access(tmp_path, depth):
    run_bench(tmp_path, "fifo_units_tb", ["-P", f"fifo_units_tb.DEPTH={depth}"])
