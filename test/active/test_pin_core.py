"""Parameterized RTL execution on the real core, not a substituted model."""

from pathlib import Path
import pytest
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "inputs,outputs", [(1, 1), (8, 8), (15, 16), (17, 9), (256, 256)]
)
def test_core(inputs, outputs):
    build = ROOT / "test/sim_build" / f"pin_core_{inputs}_{outputs}"
    runner = get_runner("icarus")
    runner.build(
        sources=[ROOT / "src/protocol_core.v", ROOT / "test/pin_core_tb.v"],
        hdl_toplevel="pin_core_tb",
        parameters={"INPUT_PINS": inputs, "OUTPUT_PINS": outputs},
        build_dir=build,
        build_args=["-g2012"],
        always=True,
    )
    runner.test(
        hdl_toplevel="pin_core_tb",
        test_module="pin_core_checks",
        test_dir=ROOT / "test",
        build_dir=build,
        results_xml=str(build / "results.xml"),
    )


@pytest.mark.parametrize("inputs,outputs", [(0, 1), (1, 0), (257, 1), (1, 257)])
def test_reject_invalid_hardware_counts(inputs, outputs, tmp_path):
    import subprocess

    executable = tmp_path / "invalid.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "pin_core_tb",
            f"-Ppin_core_tb.INPUT_PINS={inputs}",
            f"-Ppin_core_tb.OUTPUT_PINS={outputs}",
            "-o",
            str(executable),
            str(ROOT / "src/protocol_core.v"),
            str(ROOT / "test/pin_core_tb.v"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True)
    assert result.returncode != 0 and "pin counts must be 1..256" in result.stdout
