# Active verification

`uv run --locked pytest` runs test/active: typed ISA/assembler checks and five
parameterized Icarus core configurations. test/conftest.py explicitly excludes
historical root test*.py modules even when pytest is invoked on test/.
`uv run --locked make -B -C test` runs pin_examples against the wrapper;
`SIM=verilator` selects the second simulator, and `GATES=yes` selects the freshly
mapped new-design netlist. The same pin-only observations apply to RTL and gates; UART RAM/counter
inspection is required in RTL and omitted only for GATES=yes.

Core checks compare all 65,536 machine words against the typed decoder in every
pin configuration; cover all RAM addresses, pin and bank boundaries, aliasing,
loader and branch boundaries, fixed RAM/WAIT timing, reset/configuration,
pause/resume, and independent output enables.

The old root tests, runtime_units_tb.v, old ISA golden snapshot and studies are
historical source. They may be incompatible and are not coverage for pin-v1.
The active golden snapshot is golden/pin_words.json. The five top-level firmware/*.asm examples and three firmware/uart/*.asm
listings are included. See ../README.md for measured status and
../docs/physical_flow.md for the physical blocker and mapped test commands.

Current evidence: 139 Python checks pass; fifteen wrapper groups pass in both Icarus
12.0 and Verilator 5.038. The wrapper and all five parameterized cores synthesize
with Yosys 0.55 (`-noabc`). See ../docs/pin_processor_verification.json for
baseline commands, source fingerprints, synthesis results, and the physical-flow blocker.
Current UART/expanded-suite evidence is in ../docs/uart_verification.json.

Reproduce generic synthesis with `uv run --locked python -m tools.check_pin_synthesis`
(native Yosys), or supply `--yosys .asic-tools/venv/bin/yowasp-yosys` with the local
ASIC environment. This does not measure mapped area or routed timing.

## UART firmware coverage

`pin_uart` adds nine pin-level groups to the existing six wrapper groups, in both
simulators. See ../firmware/uart/README.md for pins, program timing, payload/buffer
limits, and the half-duplex echo contract. The default Makefile runs both modules.
`uv run --locked make -B -C test COCOTB_TEST_MODULES=pin_uart` selects just UART.

UART generation tests exercise file/module CLIs, clock/baud options, capacity and
payload bounds, default listings, image-size rejection, and artifact-independent
construction. All generated programs use the unchanged production ISA/core.
Historical runtime UART tests remain excluded; no results from them are reused.
