# JTAG request validation and safe rejection

2026-10-25. A **198-word JTAG candidate** now validates requests and scan lengths
before any per-request TAP activity. Two test groups pass on the existing
256-word/four-register model. The production128-word core cannot load it.
No production RTL, opcode or protocol-specific hardware is added.

The [builder](../study/protocol_exploration/build_jtag_runtime.py) combines the
generic request/event validation used by the runtime foundation with the
unchanged scan sequence from the125-word probe. It emits the
[candidate](../study/protocol_exploration/jtag_runtime_candidate.asm).
The original production probe and its verification record remain unchanged.

## Request and pin contract

Valid operation1 requests use arguments address0/length2:
`[IR_scan, final_byte_bits]`, with IR_scan0/1 and final_byte_bits1–8.
Input count must match actual buffered occupancy and be1–64 bytes. Output limit
must cover input count and not exceed64. The total scan length remains
`8 * (input_count - 1) + final_byte_bits`, or1–512 bits. Input is LSB-first;
partial final output bytes retain the probe's high alignment and metadata0.

Flags, reserved bytes and high address/length/count bytes must be zero.
Invalid fields return status1 BAD_RECORD,2 BAD_OPERATION,3 BAD_ARGUMENTS or
4 BAD_LENGTH, preserving request ID and zero detail/reserved bytes. Rejected
requests drain actual buffered input, report its count and produce no output.
No TCK, TMS, TDI or output-enable transition is permitted during rejection.
Empty scans are rejected rather than treated as an implicit reset/no-op.

The boot sequence still clocks at least five TMS-high cycles to reset the TAP,
then enters idle. These boot clocks precede request validation and are explicitly
excluded from the rejection window. After boot, rejection must preserve TAP
state, selected instruction, target data, capture count and reset count.
A subsequent valid request must scan without resetting/reloading the ASIC.

Pins remain uio0=TCK,1=TMS,2=TDI,3=TDO, output enable0x07. Protocol clock periods
are at least10 µs at the modeled50 MHz core clock, with at least5 µs high/low
and checked TMS setup. Scratch uses the16-byte request,16-byte event and one
remaining-count byte:33 bytes at128–160. All four existing registers are used.
Voltage compatibility and optional level translation remain board work; no
external JTAG controller performs the scan for the ASIC.

## Evidence and reproduction

```sh
uv run --locked pytest -q test/test_jtag_runtime_units.py
# Expected exit1:198 words exceeds production128.
uv run --locked python study/protocol_exploration/run_jtag_runtime.py jtag_runtime
uv run --locked python study/protocol_exploration/run_jtag_runtime.py jtag_runtime --expanded-model
```

The [result snapshot](jtag_runtime_results.json) records exact commands,
source/XML hashes, capacity diagnostic and unchanged physical-source hashes.
The independent [sixteen-state TAP tests](../test/test_jtag_runtime.py) reuse
the frozen probe peer's public-pin shift/capture/update model; expected bits
come from independent target registers and input payload, not DUT instructions.

Two test groups cover:

- IDCODE and writable-register/BYPASS scans, IR selection, varied independent
  data, lengths1/7/8/9/31/32/33/511/512, partial-byte alignment, clock/control
  relationships and repeated requests without reset/reload.
-30 rejected requests across flags/reserved/high bytes, operation, argument
  address/length, IR selection, final-bit range, empty input, declared/actual
  mismatch, insufficient/oversized output and64-byte draining. Pin-change
  guards and TAP snapshots prove no rejection activity. A valid nine-bit scan
  follows each table case, and a final one-bit BYPASS scan follows a rejection.

A unit test checks generated-source freshness,198-word size, ordinary16-bit
encoding and production-capacity rejection. This is functional model evidence,
not a new physical implementation. The named default production regression
continues to use the original125-word probe; CI runs this larger candidate in
a separate step.

## Remaining limits and next task

- The measured198-word image does not fit production. Further software compaction
  or generic program storage remain candidates; this size is not a lower bound
  on every possible validated JTAG implementation.
- No explicit per-request TAP reset, clock configurability, multi-TAP chaining,
  reset-during-scan, mapped verification or board interoperability is demonstrated.
- Counterfactual256-word capacity and historical source hashes do not prove
  area/timing/fit for a larger ASIC configuration.

JTAG's previously missing invalid-length/shape rejection now has model evidence
and a reproduced production-capacity blocker. The next functional task is to
attempt CAN winner reception, bounded retries, resynchronization and error-frame
recovery, preserving failures and evaluating generic firmware/ISA solutions.
