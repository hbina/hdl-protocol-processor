# Typed instruction construction audit

Python firmware generators and RTL test programs now construct `Program` values
from the typed instruction constructors in `tools.isa`. Labels are `Label` objects,
wait padding is `WAIT(...)`, and `Program.link()` produces the machine words.
No text parsing is required to construct those programs. The three UART generators
remain independent; no replacement framework or shared experiment chain was added.

## Active construction sites converted

| Source | Change |
|---|---|
| firmware/uart/transmit.py | Replace text emit/assemble with typed instructions and explicit labels |
| firmware/uart/receive.py | Replace text emit/assemble with typed instructions and explicit labels |
| firmware/uart/echo.py | Replace text emit/assemble with typed instructions and explicit labels |
| test/pin_core_checks.py | Construct all executable RAM/GPIO/ALU/wait/branch fixtures as typed programs |
| test/pin_examples.py | Construct the executable all-wrapper-pins fixture as a typed program |

`test/golden/uart_profiles.json` freezes 47 profiles from commit `c1b6dfc` before
conversion: four baud settings, multiple payloads/pins/capacities, alternate clock,
and capacity failures. Tests preserve exact word hashes, symbol addresses and
error diagnostics. The eight default assembly listings and their existing golden
snapshot remain unchanged. The processor RTL and ISA are unchanged.

## Intentional text assembly that remains

| Source | Why text is appropriate |
|---|---|
| tools/assembler.py | Public text parser and CLI for handwritten assembly |
| tools/isa.py and tools/program.py | Formatting/disassembly and documentation output |
| tools/snapshot_isa.py | Read and verify the checked-in assembly artifacts |
| test/pin_examples.py loader | Load the five handwritten introductory assembly examples |
| test/active/test_pin_tools.py | Exercise parser errors, grammar, CLI and round trips |
| test/active/test_uart_firmware.py | Verify generated listings and CLI output against assembled artifacts |
| firmware/*.asm and firmware/uart/*.asm | Human-readable input examples and generated listings, not Python builders |

Generator tests forbid text-parser calls. An import audit prevents Python firmware
and core execution fixtures from depending on the text assembler. Reserved raw
machine words in the decoder/core tests remain deliberate invalid-encoding inputs.

## Removed archival source

The obsolete runtime/experimental-ISA dependency cluster was already outside active
CI and incompatible with pin-v1. This cleanup removes 181 tracked files:

- 138 study files: predecessor generators, RTL-patching runners, peers, and old artifacts.
- 36 retired test/fixture files, including the legacy collection-ignore shim.
- Five historical firmware files/index entries.
- Two obsolete exploration budget/provenance tools.

This includes 134 Python files and 42 old assembly listings. Some archived generators
were already typed, but depended on the same removed ISA/runtime and predecessor
machinery, so the obsolete cluster was removed together. Current tests and current
protocol behavior remain covered. Historical findings and result JSON in docs are
retained; they do not become current coverage.

See [source recovery](source_history.md) for exact Git versions and commands. Old
paths appearing inside retained historical reports refer to those source versions,
not to the current checkout.

## Verification

The current result record is `typed_instruction_verification.json`. It contains
source hashes, removal inventory, all profile comparisons, and current test/XML
results. Earlier `uart_verification.json` and `pin_processor_verification.json`
remain historical verification records with their original source fingerprints.
Hardware synthesis results still apply only where the unchanged RTL hashes match;
this cleanup makes no new physical/timing/interoperability claim.
