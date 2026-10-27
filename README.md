# Programmable Pin Processor

A small autonomous processor for cycle-counted digital protocol firmware,
targeting the Jane Street protocol-emulator ASIC competition and Tiny Tapeout
IHP CMOS5L. The same parameterized Verilog core can be integrated into FPGA designs.

Input pins → synchronizers → processor ↔ RAM → output values and enables.
Firmware is uploaded separately; execution uses pins directly. There is no host
request/response transport, peripheral bus, queue, or protocol-specific engine.

## Status

**Last updated: 2026-10-27.** Incompatible pin-v1 architecture implemented;
RTL/tool verification and generic synthesis pass. Physical implementation is
**blocked**: the installed LibreLane 3.1.0.dev3 environment has no compatible
container engine. No new routed timing, area, DRC/LVS, or mapped-test claim exists.

The core has 256 × 16-bit program words, four 8-bit registers, 256 bytes of
firmware-owned RAM, and independent 1–256 input/output pin parameters. GPIO
operations take one clock; RAM loads/stores take two. Input synchronization
adds latency. The production wrapper provides 15 inputs and 16 outputs at a
50 MHz target, reserving ui[7] for configuration. See the
[architecture and ISA](docs/pin_processor.md) and [examples](firmware/README.md).

| Protocol | Status | Current scope |
|---|---|---|
| UART | Partial | RAM-backed repeating 8N1 TX, bounded continuous RX, READY-gated sequential echo; selected baud/phase/mismatch/error tests pass in both simulators. Full-duplex, parity and board interoperability remain open |
| SPI | Partial | One mode-0 byte exchange with receive storage |
| I2C | Partial | Address write, ACK/NACK sampling and clock stretching; no full transaction implementation |
| USB, Ethernet, JTAG, SWD, PS/2, CAN | Not started | Earlier experiments target the removed runtime architecture |

Historical runtime/protocol and physical results remain in
[the previous dashboard](docs/historical_runtime_status.md),
[source recovery index](docs/source_history.md), and their linked reports.
Obsolete study/runtime source and artifacts have been removed; their versions
remain recoverable from Git. They are not
coverage for this processor. The paused framework refactor is preserved only
on `bookkeeping/study-refactor-snapshot`.

## Verification

| Check | Evidence |
|---|---|
| Active Python checks | 190 passed, including 47 frozen pre-conversion profiles and parser-free construction checks; active core/UART coverage retained |
| Core simulations | Two groups in each configuration; all 65,536 instruction words checked per configuration |
| Pin-only wrapper regressions | 15 passed in Icarus 12.0 and 15 passed in Verilator 5.038, including nine UART groups per simulator |
| Strict Pyright / Ruff | 0 errors; formatter applied |
| Generic Yosys synthesis (`-noabc`) | Wrapper and five configurations pass; wrapper 14,931 cells; 256/256 core 20,483 cells |
| iCE40 FPGA synthesis, old → pin-v1 | LUT4: 3,230 → 586 (−81.86%); flip-flops: 2,851 → 174 (−93.90%); 4-Kbit RAM blocks: 3 → 2; [comparison](docs/pin_fpga_comparison.json) |
| Routed/mapped ASIC verification | Blocked before synthesis: no compatible container engine |

[Typed-construction audit](docs/typed_instruction_audit.md) records converted sites,
intentional text interfaces and removed archival code.
[Current source hashes and results](docs/typed_instruction_verification.json)
verify exact word/symbol preservation. The [earlier UART record](docs/uart_verification.json)
remains historical. The [baseline architecture/synthesis record](docs/pin_processor_verification.json)
still applies to the unchanged RTL; its older test/source snapshots remain historical. Generic cell counts are not
mapped ASIC area, timing, or physical-fit results. The FPGA comparison also uses
synthesis only: it does not establish maximum frequency or routed FPGA fit.

## Build and verify

```sh
uv sync --locked
uv run --locked pytest
uv run --locked pyright
uv run --locked make -B -C test
uv run --locked make -B -C test SIM=verilator
uv run --locked python -m tools.assembler firmware/pin_copy.asm --disassemble
uv run --locked python -m tools.snapshot_isa
# With native Yosys, or add --yosys /path/to/yowasp-yosys:
uv run --locked python -m tools.check_pin_synthesis
uv run ruff format .
```

Install Icarus Verilog and Verilator >=5.036 to run both simulators; CI builds
the tested Verilator 5.038 release. A local source build can be selected with
`export PATH="$PWD/.asic-tools/verilator/bin:$PATH"`. Obsolete runtime/study
tests have been removed; no legacy collection shim is needed. All Python tools
use uv; no dependency changes are required. See [the physical flow](docs/physical_flow.md)
for the pinned ASIC toolchain and new-design build commands.

## Roadmap and limitations

- [x] Replace host requests/queues with direct, parameterized pin access and private RAM.
- [x] Expand instruction memory to 256 words and define the incompatible pin-v1 ISA.
- [x] Add independent pin-copy, capture/replay, UART, SPI, and I2C examples.
- [x] Complete and record the active RTL/tool/synthesis verification.
- [x] Use typed instructions in all Python builders/test programs and remove obsolete archival code.
- [ ] Restore the physical tool environment and route the new 6×4, 50 MHz implementation.
- [ ] Pass new mapped regressions and all configured timing/DRC/LVS checks.
- [x] Finish and record UART RAM TX/RX/echo, timing and error-recovery verification.
- [ ] Add simultaneous UART TX/RX and additional framing options when required.
- [ ] Extend protocol firmware and validate external hardware interoperability.

RAM/program storage is uninitialized at reset; firmware must initialize RAM and
a complete valid program must be loaded before execution. Pin counts above the
wrapper's 15/16 are core configurations, not additional physical ASIC pads.
UART echo requires a sender that waits for READY plus an idle bit; traffic while
echo is busy may be lost or misframed. RX-only buffers drop new bytes when full
and require restart/reload to reclaim space. UART framing is currently 8N1 only.
See [the UART guide](firmware/uart/README.md) for capacities, pins, counters and
clock/baud limits.

Board validation, CDC/MTBF signoff, full protocol coverage, production physical
fit/timing, and realistic power/IR analysis remain open. The prior runtime
capacity figures and mapped tests do not establish results for this revision.

## Repository

- `src/`: processor, Tiny Tapeout wrapper, and physical configuration.
- `firmware/`: five introductory assembly examples and three standalone UART programs.
- `tools/`: typed ISA, assembler, linker, and active firmware snapshots.
- `test/active/`: active Python and parameterized-core regressions.
- `test/pin_examples.py`: pin-only RTL/mapped example checks.
- `study/`: retired source recovery index; reports remain in docs.
- `docs/`: current architecture and preserved historical evidence.
