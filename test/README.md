# Active verification

`uv run --locked pytest` runs test/active: typed ISA/assembler checks and five
parameterized Icarus core configurations. test/conftest.py explicitly excludes
historical root test*.py modules even when pytest is invoked on test/.
`uv run --locked make -B -C test` runs pin_examples against the wrapper;
`SIM=verilator` selects the second simulator, and `GATES=yes` selects the freshly
mapped new-design netlist. The same six pin-only tests apply to RTL and gates.

Core checks compare all 65,536 machine words against the typed decoder in every
pin configuration; cover all RAM addresses, pin and bank boundaries, aliasing,
loader and branch boundaries, fixed RAM/WAIT timing, reset/configuration,
pause/resume, and independent output enables.

The old root tests, runtime_units_tb.v, old ISA golden snapshot and studies are
historical source. They may be incompatible and are not coverage for pin-v1.
The active golden snapshot is golden/pin_words.json. Only the five top-level
firmware/*.asm examples are included. See ../README.md for measured status and
../docs/physical_flow.md for the physical blocker and mapped test commands.

Current evidence: 79 Python checks pass; six wrapper groups pass in both Icarus
12.0 and Verilator 5.038. The wrapper and all five parameterized cores synthesize
with Yosys 0.55 (`-noabc`). See ../docs/pin_processor_verification.json for
commands, source fingerprints, results, and the physical-flow blocker.

Reproduce generic synthesis with `uv run --locked python -m tools.check_pin_synthesis`
(native Yosys), or supply `--yosys .asic-tools/venv/bin/yowasp-yosys` with the local
ASIC environment. This does not measure mapped area or routed timing.
