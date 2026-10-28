import json
from pathlib import Path
import re
import subprocess

from combhdl import compile
from examples.combinational.demo import demo

ROOT = Path(__file__).resolve().parents[2]


def test_generated_demo_is_current():
    assert (ROOT / "src/combhdl_demo.v").read_text() == compile(demo).verilog


def test_board_metadata_and_physical_configuration():
    metadata = (ROOT / "info.yaml").read_text()
    assert re.search(r"clock_hz:\s+0\b", metadata)
    assert 'tiles: "6x4"' in metadata
    assert 'top_module:  "tt_um_combhdl_demo"' in metadata
    sources = re.findall(r'^    - "([^"]+\.v)"', metadata, re.MULTILINE)
    assert sources == ["project.v", "combhdl_demo.v"]
    assert all((ROOT / "src" / file).is_file() for file in sources)
    makefile = (ROOT / "test/Makefile").read_text()
    assert "PROJECT_SOURCES = " + " ".join(sources) in makefile
    config = json.loads((ROOT / "src/config.json").read_text())
    assert config["CLOCK_PORT"] == [] and config["RUN_CTS"] == 0
    for key in ("FALLBACK_SDC", "PNR_SDC_FILE", "SIGNOFF_SDC_FILE"):
        assert config[key] == "dir::pins.sdc"
    assert config["CLOCK_PERIOD"] == 20
    assert len(config["PNR_CORNERS"]) == 3


def test_sdc_tcl_contract(tmp_path):
    # Exercise Tcl syntax and conditional PDK constraints with an STA command spy.
    # Actual OpenSTA/PDK timing validation still requires the physical toolchain.
    sdc = str(ROOT / "src/pins.sdc")
    for optional in (False, True):
        script = """
set calls {}
foreach name {create_clock set_input_delay set_output_delay set_driving_cell set_load set_max_fanout set_max_transition set_max_capacitance set_clock_uncertainty set_clock_transition set_timing_derate} {
    proc $name {args} {global calls; lappend calls [linsert $args 0 [lindex [info level 0] 0]]}
}
proc all_inputs {} {return INPUTS}
proc all_outputs {} {return OUTPUTS}
proc current_design {} {return DESIGN}
proc get_clocks {name} {return $name}
set env(SYNTH_DRIVING_CELL) driver/Y
set env(OUTPUT_CAP_LOAD) 5
set env(MAX_FANOUT_CONSTRAINT) 8
set env(CLOCK_UNCERTAINTY_CONSTRAINT) 0.1
set env(CLOCK_TRANSITION_CONSTRAINT) 0.1
set env(TIME_DERATING_CONSTRAINT) 5
"""
        if optional:
            script += "set env(MAX_TRANSITION_CONSTRAINT) 0.2\nset env(MAX_CAPACITANCE_CONSTRAINT) 0.3\n"
        script += f"source {{{sdc}}}\nforeach call $calls {{puts $call}}\n"
        harness = tmp_path / "sdc.tcl"
        harness.write_text(script)
        result = subprocess.run(
            ["tclsh", str(harness)], check=True, capture_output=True, text=True
        )
        commands = result.stdout.splitlines()
        assert "create_clock -name comb_reference -period 20" in commands
        assert "set_input_delay 0 -clock comb_reference INPUTS" in commands
        assert "set_output_delay 0 -clock comb_reference OUTPUTS" in commands
        assert "set_driving_cell -lib_cell driver -pin Y INPUTS" in commands
        assert "set_load 0.005 OUTPUTS" in commands
        assert ("set_max_transition 0.2 DESIGN" in commands) == optional
        assert ("set_max_capacitance 0.3 DESIGN" in commands) == optional
