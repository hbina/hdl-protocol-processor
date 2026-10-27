# Active verification

`uv run --locked pytest` runs test/active: ISA/assembler behavior, five parameterized
Icarus core configurations, UART generation, and typed-construction regressions.
Retired root tests, the old runtime testbench/golden snapshot, and the collection
ignore shim have been removed. `uv run --locked pytest test` selects the same suite.

`uv run --locked make -B -C test` runs pin_examples and pin_uart against the wrapper.
`SIM=verilator` selects the second simulator, and `GATES=yes` selects a newly mapped
netlist. Pin-only observations apply to RTL and gates; UART RAM/counter inspection
is required in RTL and omitted only for GATES=yes. No new mapped results exist.

Core tests cover all 65,536 instruction words in each configuration, all RAM
addresses, fixed access/wait timing, pin and bank boundaries, aliasing, reset,
configuration, pause/resume, the complete loader, and branch/PC boundaries. Executable
core and wrapper fixtures use typed instructions; text is used only for assembler
behavior and loading checked-in assembly files.

`golden/pin_words.json` covers the five introductory assembly programs and three
UART listings. `golden/uart_profiles.json` preserves words, symbols and capacity
errors for 47 pre-conversion profiles from c1b6dfc. Default listings stay unchanged.

UART contributes nine of the fifteen pin-level wrapper groups. It covers all byte
values, repeated RAM TX, exact edge spacing, bounded back-to-back RX, baud/phase
variation, errors/break recovery, and the sequential echo READY contract. See
../firmware/uart/README.md for pins, capacities, counters and traffic limits.

Use `COCOTB_TEST_MODULES=pin_uart` with make to select UART only. Run generic synthesis
with `uv run --locked python -m tools.check_pin_synthesis`; use
`--yosys .asic-tools/venv/bin/yowasp-yosys` with the local ASIC environment.

Current evidence is in ../docs/typed_instruction_verification.json. Earlier UART and
hardware records remain historical; hardware synthesis applies to unchanged RTL.
No routed timing/area, CDC/MTBF, or real-device interoperability result is implied.
See ../docs/physical_flow.md for the existing container-engine blocker and
../docs/source_history.md for retired source recovery.
