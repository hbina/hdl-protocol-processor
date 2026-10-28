> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Historical runtime dashboard

Source links/commands below refer to retired versions. Use the
[Git recovery index](source_history.md) for files removed from the current checkout.

Superseded by the pin-driven architecture on 2026-10-26. All results below
apply to the old source tree, not to the current RTL.

# Programmable Protocol Emulator ASIC

An open-source, cycle-accurate protocol engine targeting Jane Street's protocol
emulator ASIC competition and the Tiny Tapeout IHP 130 nm CMOS5L process.

The [archived organizer email and FAQ](docs/competition_email.md) records the
competition guidance supplied by the project owner, including the January 18,
2027 submission deadline, protocol expectations, and submission requirements.

Version 0.2 implements a reloadable 128-word 16-bit instruction engine, four
8-bit registers, 256-byte data memory, bounded runtime queues, an asynchronous
request/acknowledgement interface, and direct control of eight protocol pins. Example firmware implements UART, SPI, and I2C.
Protocol behavior is intentionally defined by uploaded firmware: future RTL
extensions must be reusable programmable facilities, not UART-, SPI-, I2C-, or
other protocol-specific engines.

## Project status

**Last updated:** 2026-10-25

The historical [nine-protocol acceptance audit](docs/protocol_acceptance_audit.md)
records initial TX/RX experiments for every protocol, seventeen passing source/XML
records and seventeen reproduced production program-capacity failures. The full goal
remains open: remaining CAN counter/timing/fault rules are unfinished.
These missing features are not reproduced architectural blockers. **Next priority:**
extend TX-tail handling and overload-fault accounting on the compact CAN model.

The latest [passing CAN image](docs/can_flag_compact_study.md) uses all1,024
model words. Five active-flag fault/restart groups, five post-flag counter groups
and two selected RX regressions pass. Counter updates, flags, retries and phase
handling remain generic firmware. No new RTL/ISA/RAM was added. Production
rejects1,024>128; full CAN timing/confinement and ASIC fit remain open.
Earlier [phase](docs/can_resync_study.md), [winner/retry](docs/can_winner_study.md)
and [fault-counter](docs/can_fault_state_study.md) studies retain their evidence
and failing comparisons; the detailed verification table below tracks them.

The [original tail investigation](docs/can_tail_study.md) preserves three
old-image wire failures and an unverified 1,067-word draft. The separate
[compact tail candidate](docs/can_tail_compact_study.md) fits 1,024 model words
and freshly passes all seven selected RX-tail/overload groups. Full CAN behavior
and production fit remain open. After the typed-ISA migration, all 155 project
unit tests pass and strict Pyright reports zero errors. The aggregate provenance
audit now verifies 17 saved source/XML records and reproduces 17 production
capacity failures. See [migration verification](docs/typed_isa_verification.json).
The earlier [pre-migration verification](docs/commit_verification.json) remains
historical evidence; its 57-unit count and failed provenance audit describe that
earlier source tree.

The [validated UART runtime candidate](docs/uart_runtime_study.md) now passes
the specified request ABI, input draining, clock deadlines and reset/recovery
checks on the generic eight-register model. Six RTL groups and all 56 unit tests
pass. Quiet deadlines measure exactly 65,536 clocks per window; false starts
consume clock budget rather than replenishing it. The 251-word image exceeds
production capacity, so it remains in `study/` and the named production image
is still blocked. No timer hardware or production RTL was added.

The [validated JTAG candidate](docs/jtag_runtime_study.md) now rejects invalid
envelopes/lengths, drains input and preserves the TAP before a subsequent valid
scan. Two model groups and one new unit pass, covering 30
rejections. It uses 198 words on the existing 256-word/four-register model and
also exceeds production capacity. No scan timing or RTL feature was changed.

[Bidirectional exploration of all nine protocols](docs/protocol_exploration.md)
is underway, with protocol behavior entirely in generic-ISA firmware. New
UART and SPI probes exchange arbitrary runtime payloads through 64 bytes and
repeat requests without reload/reset on the unchanged 128-word core. JTAG
adds TAP reset, IR selection and DR scans through 512 bits with readback;
these images use 107, 72 and 125 words. These production probes accept valid
requests only; the full UART ABI now passes separately on the larger model. See
[probe contracts and evidence](docs/protocol_probe_results.md).
The 25 baseline unit tests and ten Icarus RTL integration tests pass. Physical results
and the five mapped baseline tests remain the recorded 2026-10-07 evidence;
the new probes have no mapped or hardware interoperability coverage yet.

The [I2C TX/RX capacity study](docs/i2c_capacity_study.md) now reproduces a
program-space blocker: its 249-word candidate exceeds the actual 128-word
limit. Five tests pass on an isolated 256-word model, including multi-byte
read/write, repeated START, ACK/NACK, stretching, bus clear and recovery.
That model is not a supported ASIC configuration and has no physical results;
production RTL and its existing physical-source hashes are unchanged.

[SWD and PS/2 experiments](docs/wave_b_results.md) now pass two tests each on
explicit 256-word models, including direction/parity/ACK and failure recovery.
Their 230- and 188-word candidates also fail the actual 128-word limit. Six
protocols had initial firmware/peer experiments at that checkpoint.
Capacity-model results are not production ASIC coverage.

The [Ethernet experiment](docs/ethernet_capacity_study.md) now demonstrates
minimum-frame TX/RX at 10 Mbit/s with firmware FCS, by buffering a frame and
calculating CRC offline. Six tests pass on an explicit 512-word generic-address
model, including RX phase/frequency and PHY-shaped TX setup checks. Its
280-word image exceeds the actual 128-word limit; streaming traffic, real-PHY
integration and physical fit remain unverified.

The [CAN experiments](docs/can_transmit_study.md) demonstrate 125 kbit/s RX and
TX in separate firmware images, with four tests each on the explicit 512-word
model. The 335-word RX and 318-word TX images both exceed actual capacity.
A combined 622-word source fails the 512-word limit. The
[generic frontier model](docs/generic_frontier_study.md) now runs a copy on an
isolated 1024×18/eight-register core: alternating CAN TX/RX and recovery pass
without reloading. Three model tests, three ISA unit tests and the ten legacy
RTL tests pass there. Separate701-/811-word follow-ups add ACK-error flags/retry
and winner reception/retained-payload retry on that same generic model.
The819-word follow-up adds bounded RX phase correction. Production capacity,
full TX/RX synchronization rules and complete error handling remain open.

The [USB enumeration study](docs/usb_enumeration_study.md) now runs a 1,012-word
firmware image through reset, descriptor reads, deferred address assignment,
configuration selection and arbitrary vendor control write/readback. Ten model
groups pass. Descriptor retries and short interpacket gaps
pass after firmware scheduling changes; the retained 991-word comparison still
misses the next IN. Protocol behavior remains entirely generic instructions on
the isolated CALL/carry model. Production fit, full request/jitter coverage and
host-OS/hardware interoperability remain open; 12 model instruction words remain.

Earlier USB experiments remain reproducible: [buffered receivers](docs/usb_receive_study.md)
still fail turnaround (~140/~126 µs versus 4.33 µs), while
[live RX](docs/usb_live_study.md), [compact token handling](docs/usb_out_study.md),
[bidirectional packet firmware](docs/usb_in_study.md), and
[live TX/autonomous vendor controls](docs/usb_control_study.md) and
[reset/address handling](docs/usb_address_study.md) preserve their
separate evidence. All nine protocols have initial experiments; the full
bidirectional goal stays open.

The generic runtime foundation is implemented and verified at RTL and gate level:
load firmware once, submit bounded ECHO/XOR requests, and retrieve matching
results without resetting execution. Protocol semantics remain in firmware.
The existing UART/SPI/I2C examples still pass. The expanded core now fits the
6x4 allocation and passes extracted setup/hold timing at 50 MHz in all three
process corners, with zero routing DRC, Magic DRC, LVS, and slew violations.
All five mapped integration tests pass and the configured RTL-to-GDS flow is
complete. Earlier control/decoder timing failures
were resolved by draining issued accesses and using local storage permission
checks; firmware accesses still take two cycles.

Runtime v1 permits one outstanding request with up to 64 input/output entries.
Physical builds explicitly set eight OpenROAD threads to avoid the pinned
LibreLane `None` thread-count fallback.
See [the runtime specification](docs/runtime.md) for ownership, pin transport,
ISA extensions, firmware ABI, and the controller library.

### Challenge protocol coverage

[Jane Street names nine protocol targets](https://blog.janestreet.com/protocol-emulator-asic-competition/).
`Verified` means the implemented scope has automated RTL and post-route
gate-level coverage; it does not imply that every optional mode or role in the
protocol standard is implemented. For this project, a protocol is not considered
fully supported until its selected role can transmit and receive arbitrary
payload data; supporting every possible controller, peripheral, host, or target
role is a separate scope decision.

| Priority | Protocol | Status | Implemented and verified scope | Next milestone |
|---|---|---|---|---|
| Baseline | UART | Partial | Production:107-word valid-request TX/RX probe; model:251-word validated runtime ABI, software clock deadlines, phase/error/reset tests; mapped: original fixed-byte TX example | Resolve251-word/eight-register production capacity and add mapped/board coverage |
| Baseline | SPI | Partial | RTL: mode-0 controller with CS and arbitrary multi-byte TX/RX through 64 bytes at 100 kHz; mapped: original 8-bit example | Add request validation, configurable timing/modes 1–3 and mapped coverage |
| Baseline | I2C | Partial | ASIC example: address write/ACK/stretch; capacity study: multi-byte TX/RX/recovery on a 256-word model only | Resolve the 249-word candidate's capacity blocker; validate production RTL/mapped behavior |
| Stretch | Low-speed USB | Partial | Isolated CALL/carry model: selected enumeration sequence, descriptor DATA toggles/retries, configuration state and arbitrary EP0 vendor write/readback | Extend request/jitter/reset coverage and resolve production storage/physical timing; validate OS/board interoperability |
| Stretch | 10 Mbit Ethernet | Partial | 512-word model only: minimum-frame 10 Mbit/s SNI TX/RX with firmware FCS, clock phase/duty tests and malformed-frame checks | Resolve 280-word capacity blocker; validate PHY/carrier timing, larger/streamed frames and physical implementation |
| Suggested | JTAG | Partial | Production:125-word valid-scan probe; model:198-word validated requests, 1–512-bit scans and safe rejection/recovery | Resolve production capacity; add explicit reset/clock options and mapped/board coverage |
| Suggested | SWD | Partial | 256-word model only: DP reads/writes, turnaround, parity, bounded WAIT and FAULT/ABORT recovery | Resolve 230-word capacity blocker; extend validation and production/mapped coverage |
| Suggested | PS/2 | Partial | 256-word model only: host command/link ACK, 64-byte RX, odd parity and clock/framing recovery | Resolve 188-word capacity blocker; extend validation and production/mapped coverage |
| Suggested | CAN bus | Partial | Generic models only:1,024-word TX/RX/winner/retry, selected active/passive RX/TX flags and bit-error restarts, post-flag counters and bus-off/recovery; selected drift/step tests pass | Add remaining timing/counter/EOF/overload/busy-bus rules; resolve production storage/physical cost |

### Verification snapshot

| Check | Latest result |
|---|---:|
| Post-migration project units / strict type check | 155 passed / 0 errors; [evidence](docs/typed_isa_verification.json) |
| Historical pre-migration units / production RTL / compact CAN tails | 57 / 10 / 7 passed; [earlier evidence](docs/commit_verification.json) |
| Assembler unit tests | 16 passed |
| Typed ISA model / program builder / RTL-and-doc sync units | 36 / 14 / 2 passed; strict `pyright` 0 errors on `tools/isa.py`, `tools/program.py`, `tools/assembler.py` and study `isa_variants.py`/`fragments.py` |
| ISA golden snapshot (`test/test_isa_golden.py`) | 46 passed; all 45 checked-in programs bit-identical under all six `IsaConfig` variants (124 encodings, 146 pinned errors) |
| Runtime storage/FIFO unit tests | 5 passed |
| Controller ABI/recovery unit tests | 4 passed |
| Icarus RTL protocol/runtime/probe regression | 10 passed |
| I2C expanded-capacity model (not production ASIC) | 5 passed; 249-word image rejected by actual 128-word limit |
| SWD / PS/2 expanded-capacity models (not production ASIC) | 2 / 2 passed; 230-/188-word images rejected by actual 128-word limit |
| Ethernet expanded-capacity model (not production ASIC) | 6 passed; 280-word image rejected by actual 128-word limit |
| CAN RX / TX expanded-capacity models (not production ASIC) | 4 / 4 passed separately; 335-/318-word images exceed 128; combined 622 exceeds that 512-word model |
| USB packet baseline / compact models (not production ASIC) | 5 / 5 passed; 400-/391-word images exceed 128; separate turnaround tests both fail (~140/~126 µs vs 4.33 µs) |
| Frontier ISA units / combined-CAN model tests | 3 / 3 passed; 1024×18/eight registers only |
| Legacy RTL regression on frontier model | 10 passed; separate from production/mapped evidence |
| Core-only generic synthesis, production / frontier | 5,647 / 40,452 cells (`synth -noabc`); no mapped area/timing/fit claim |
| Live USB / generic leaf-call model | 5 passed; 947 words; packet ACK 2.435–2.634 µs in tested sweep; no enumeration proof |
| Leaf-call encoding/CRC units / legacy RTL on call model | 4 / 10 passed |
| Core-only unmapped synthesis with leaf call | 40,510 generic cells; 58 above the previous frontier, including 10 link flops |
| Compact USB / addressed OUT-SETUP on carry model | 6 / 4 passed; 310 / 403 words; transaction sweep ACK 2.792–3.077 µs at minimum token-to-data gap |
| Carry encoding/compatibility/source units | 3 passed |
| Legacy RTL regression on carry model | 10 passed; production/mapped evidence unchanged |
| Core-only unmapped synthesis with carry | 40,545 generic cells; 35 above the leaf-call model; no physical-fit proof |
| Combined USB IN/OUT-SETUP model / new units | 6 / 2 passed; 629 words; IN response sweep 1.916–2.051 µs |
| Live USB TX / autonomous vendor-control models | 6 / 3 passed; 648 / 776 words; control response sweep 2.129–3.979 µs; no runtime-host intervention between control stages |
| Live TX CRC-seed/source unit tests | 2 passed |
| USB reset/address model / new units | 6 / 2 passed; 921 words; address sweep 2.077–3.993 µs |
| Minimal USB enumeration model / new units | 10 / 2 passed; 1,012 words; descriptor phase/rate responses 2.100–3.467 µs |
| USB short-gap comparison | Retained 991-word candidate fails with missing IN response; fixed image passes the same test |
| UART runtime model / new units | 6 / 2 passed; 251 words; 28 malformed cases and exact quiet deadlines |
| Validated JTAG model / new unit | 2 / 1 passed; 198 words; 30 rejections with pin/TAP stability and recovery |
| CAN ACK-recovery model / new unit | 3 / 1 passed; 701 words; flags/retry/exhaustion/dominant-bus recovery |
| CAN winner-recovery model / new unit | 3 / 1 passed;811 words;11 loss positions, retained payload, multiple winners, shared attempt cap |
| CAN bounded RX phase model / new unit | 3 / 1 passed;819 words;±5,000 ppm and400 ns steps; retained fixed-clock case fails with no ACK |
| CAN fault-state model / new units | 5 / 2 passed;1,020 words;persistent counters, equal-polarity passive flags, bus-off/recovery;1,092-word inlined prototype exceeds model capacity |
| CAN RX flags/compaction model / new unit | 5 / 1 passed;1,021 words after48-word saving;8 timed active flags;52 total units; old local-error-only image fails CRC-flag check |
| CAN post-flag counters model / new unit | 5 / 1 passed;1,023 words;53 total units;18 timing rows at400-clock spacing; old image fails REC1 vs9 |
| CAN flag-bit investigation / new unit | Old image:2 counter failures,1 passive control passed; draft1,076>1,024 model;54 total units; draft behavior unverified |
| CAN compact flag-error/restart model / regressions / new unit | 5 fault +5 post-flag +2 selected RX groups passed;55 total units;1,024 words after52-word saving;58 restart samples at400 clocks |
| CAN tail investigation / new unit | Old image:3 wire failures,1 ordinary-frame control passed;1,067-word draft exceeds model1,024;56 total units; draft unverified |
| Nine-protocol evidence/capacity audit | Rechecked 2026-10-25 after the typed-ISA migration: 17 saved passing source/XML records verified and 17 production size failures reproduced; [audit evidence](docs/protocol_acceptance_results.json). This check does not rerun simulations or prove full protocol acceptance |
| Verilator RTL baseline regression | 5 passed (historical; probes not rerun) |
| Post-route runtime regression | 5 passed (Icarus, CMOS5L functional models) |
| Baseline post-route UART/SPI/I2C regression | Passed for v0.1 |
| LibreLane CMOS5L flow | v0.2 complete; final GDS generated |
| Non-filler standard cells | 43,642 |
| Standard-cell area | 714,224 µm² |
| Standard-cell utilization | 79.15% |
| Worst setup slack at 20 ns, all three corners | +0.521 ns |
| Worst hold slack, all three corners | +0.105 ns |
| Route DRC / Magic DRC / LVS errors | 0 / 0 / 0 |
| Antenna / disconnected-pin / power-grid violations | 0 / 0 / 0 |
| Maximum-slew violations | 0 |
| Maximum-fanout violations | 438 (requires review) |

The final flow metrics are in `runs/runtime_direct/final/metrics.json`, and GDS
is in `runs/runtime_direct/final/gds/tt_um_protocol_emulator.gds`.
The v0.1 baseline used 14.67% of the same allocation.
Test commands, final metrics, and source/artifact hashes are recorded in
[the runtime verification record](docs/runtime_results.json).
See [the baseline design report](docs/design.md) for historical results and
[the physical-flow guide](docs/physical_flow.md) for exact reproduction steps.

### Roadmap

- [x] Specify nine bidirectional protocol experiments and the first UART runtime
      milestone; record reproducible firmware-size and timing budgets.
- [x] Complete initial TX/RX attempts for all nine protocols using generic-ISA
      firmware, with selected model/production evidence and capacity failures.
- [x] Verify the specified UART ABI/deadline/error/reset contract on a generic
      model; preserve its251-word production capacity failure.
- [x] Test JTAG invalid request/length rejection and subsequent scans on the generic
      model; preserve its198-word production capacity failure.
- [ ] Close CAN node-recovery and remaining test/physical decision gates; promote
      the validated UART/JTAG images after capacity work.
- [x] Demonstrate runtime arbitrary-payload UART TX/RX and SPI controller TX/RX
      in RTL on the unchanged core; preserve incomplete validation/coverage gaps.
- [x] Reproduce I2C program-capacity failure and test TX/RX plus bounded recovery
      on an explicit larger-program model; keep production capacity unresolved.
- [x] Attempt JTAG, SWD and PS/2 with independent peers; JTAG runs on production
      RTL, while SWD/PS2 preserve reproduced capacity blockers and model results.
- [x] Attempt minimum-frame 10 Mbit/s Ethernet TX/RX with software FCS and an
      independent serial PHY model; preserve capacity and integration gaps.
- [x] Demonstrate CAN standard-frame RX with live firmware CRC/ACK on a larger
      model; preserve capacity blocker and incomplete CAN node behavior.
- [x] Demonstrate CAN TX firmware CRC/stuffing, ACK/bit checks and arbitration-loss
      release on a larger model; preserve separate-image evidence and combined blocker.
- [x] Test combined CAN TX/RX on an isolated generic 1024×18/eight-register model;
      preserve production capacity failure and measure preliminary storage cost.
- [x] Test firmware ACK-error active flags, bounded retries and subsequent RX
      on that model; preserve the701-word production capacity failure.
- [x] Test firmware arbitration-winner reception/ACK, retained-payload retry and
      shared attempt cap on that model; preserve the811-word production failure.
- [x] Reproduce fixed-clock CAN RX drift failure and test bounded falling-edge
      phase correction in819-word firmware; preserve full timing-rule limits.
- [x] Test persistent CAN counters, selected active/passive TX signaling, bus-off
      output disable and monitored recovery on the generic call model; preserve
      fixed-flag/inlining failures and the1,020-word production failure.
- [x] Test timed CAN RX CRC/stuff/selected form flags and firmware compaction on
      that model; preserve1,069-word capacity and missing-CRC-flag comparisons.
- [x] Test receiver first-post-flag and repeated prolonged-dominant counter
      increments on the1,023-word model; preserve old-counter and size failures.
- [x] Reproduce RX/TX active-flag bit-error counter gaps with an independent
      transceiver-fault peer; preserve the1,076-word draft’s capacity failure.
- [x] Compact the active-flag bit-error draft to1,024 words and verify selected
      counter/restart/threshold behavior and earlier CAN regressions.
- [x] Reproduce CAN RX tail gaps with an independent peer and preserve the
     1,067-word draft/model-size failure.
- [x] Compact the RX tail/overload draft to 1,024 words and pass seven model groups.
- [ ] Complete TX tails and overload-flag fault accounting.
- [ ] Resolve production CAN storage/physical implementation and complete
      remaining counter/timing/EOF/overload/fault/busy-bus handling.
- [x] Attempt USB packet RX/CRC and diagnostic ACK using generic firmware;
      preserve capacity and turnaround failures plus a firmware-only optimization.
- [x] Meet the USB packet response window on an isolated generic model with live
      decode/CRC and leaf subroutines; preserve code-size and physical limitations.
- [x] Reduce USB receiver size with generic carry operations; test addressed
      OUT/SETUP, CRC5 filtering and minimum token-to-data spacing on the model.
- [x] Demonstrate arbitrary USB IN payloads with firmware CRC/stuffing, host ACK,
      retry and alternating IN/OUT requests on one isolated-model image.
- [x] Compute USB TX CRC/encoding live and test an autonomous address0/EP0 vendor
      control write/status/read/status pair, with short gaps and retry coverage.
- [x] Test firmware bus reset, deferred SET_ADDRESS and vendor controls at assigned
      addresses, including full reset/recovery duration on the isolated model.
- [x] Demonstrate selected USB enumeration with descriptor chunks/toggles,
      configuration state and arbitrary vendor control traffic on the model.
- [ ] Extend USB request/error/status service, jitter/clock-recovery/reset coverage
      and production physical implementation; validate hardware interoperability.
- [x] Implement the programmable GPIO processor and loader.
- [x] Add an assembler and example firmware workflow.
- [x] Model instructions as a typed sum type (`tools/isa.py`) with exhaustive,
  type-checked encode/decode; build test and study programs from typed values
  instead of assembly text; replace the five text-patched study assemblers with
  `IsaConfig` variants ([design §4/§6](docs/design.md)).
- [x] Demonstrate UART TX, SPI mode 0, and I2C address-write signaling.
- [x] Pass RTL and post-route gate-level regression.
- [x] Complete the pinned CMOS5L RTL-to-GDS flow.
- [x] Implement bounded generic runtime memory, queues, request/result firmware,
      and controller access; pass RTL verification without protocol-specific RTL.
- [x] Validate the runtime foundation with a new mapped netlist and physical flow.
- [ ] Extend runtime buffering to streaming requests and design/verify generic
      concurrency and configurable timed-I/O facilities.
- [ ] Complete bidirectional, configurable UART support in firmware on the
      generic programmable architecture.
- [ ] Complete configurable, arbitrary multi-byte SPI TX/RX, modes 0–3, and
      transaction framing in firmware on the generic programmable architecture.
- [ ] Complete bidirectional, multi-byte I2C controller read/write transactions
      in firmware on the generic programmable architecture.
- [ ] Implement and verify JTAG, SWD, and PS/2.
- [ ] Implement and verify classical CAN with an external transceiver.
- [ ] Implement and verify low-speed USB.
- [ ] Implement and verify the agreed 10 Mbit Ethernet scope.
- [ ] Add randomized/reference-model and formal verification.
- [ ] Run FPGA interoperability tests with physical devices.
- [ ] Resolve remaining physical-signoff caveats.

### Known limitations and signoff gaps

- The instruction sum type exists only in Python. The RTL keeps hand-written
  `OP_*` localparams (Verilog-2005/Yosys have no tagged unions, and the RTL is
  frozen by the physical baseline); `test/test_isa_sync.py` detects drift but
  does not prevent it. Study `expanded_source()` functions still derive widened
  RTL by exact text replacement on `protocol_core.v`; only the assembler side is
  typed. Instruction semantics are modelled only for cycle counts; there is no
  Python reference simulator.
- Generated study candidates (`*_candidate.asm`) were regenerated in the typed
  model's canonical listing format (decimal operands). Their words and labels
  are unchanged, but study documents quoting the old text spelling (for example
  `0x22`) no longer match the listings character for character.
- The acceptance audit verifies source/result integrity and capacity diagnostics;
  it does not prove the full protocol contracts. UART's named test and model
  candidate now exist; the production image is blocked by251-word/eight-register
  requirements. JTAG rejection now passes on a198-word model candidate; CAN node
  recovery remains open.
  The post-migration aggregate audit passes for its 17 recorded source/XML
  pairs. It requires matching saved simulator artifacts, which are not tracked
  in Git; a fresh checkout must regenerate them before running the audit.
  The earlier pre-migration verification record retains its historical hashes
  and audit failure and is not evidence for the current instruction model.
  See the audit for the requirement matrix and next implementation task.
- UART/SPI/JTAG exploration probes have RTL TX/RX evidence for valid requests only.
  The compact production probes ignore request operation/shape validation and
  UART's production probe uses a poll-count timeout without initial idle-high
  qualification. Its new251-word model candidate fixes validation/deadline/idle
  qualification and has reset-in-transfer tests; production/mapped/board coverage
  remains unresolved. I2C's TX/RX candidate needs 249 words and cannot load on the actual
  core; a 256-word model passes five tests but has no area/timing/signoff result.
  SWD/PS2 candidates need 230/188 words and pass only on larger-capacity models;
  request validation, some target modes and hardware/mapped coverage remain open.
  Ethernet's 280-word minimum-frame candidate passes only on a 512-word model.
  CAN's 335-word RX and 318-word TX candidates pass separately on 512-word
  models. A copy of the 622-word combined source passes on the larger frontier
  model; production 128-word and prior 512-word capacity failures remain.
  The701-word follow-up adds missing-ACK active flags and at most three attempts;
  the811-word candidate adds winner reception/ACK and retained-payload retry on
  that model. It cannot receive during output decoding/retry preparation.
  The819-word candidate adds bounded falling-edge RX correction, but full SJW
  rules, TX resynchronization and larger/late phase-error handling are absent.
  The1,020-word call-model candidate adds persistent TEC/REC and selected TX
  active/passive/bus-off/recovery behavior. The1,021-word follow-up adds timed
  RX CRC/stuff/selected form flags and selected valid-frame drift tests. The
  1,023-word follow-up adds receiver first-post-flag+8 and repeated prolonged-
  dominant+8 counting within a32-sample delimiter budget. The1,024-word
  compact image now adds selected active-flag RX/TX bit-error accounting and
  restarts, preserving its1,076-word failure and old-image counter negatives.
  Broader co-occurring/late-form accounting and full TX-tail, overload-fault
  and continuous-node behavior remain open. Three RX tail gaps now
  retain old-image wire counterexamples; the 1,067-word draft fails model
  capacity. A separate 1,024-word compact candidate now passes seven selected
  RX-tail groups. Its bounded overload service does not yet implement
  overload-flag bit-error/prolonged-dominance or full delimiter form rules. Recovery is
  explicitly requested; local aborts do not implement complete confinement.
  Buffered USB decoding/CRC still miss ACK turnaround; the live
  packet implementation meets the tested window only on an isolated call model.
  Addressed OUT/SETUP reception and arbitrary IN transmission now pass together
  on the carry model only. Live TX removes waveform preparation; an autonomous
  vendor-control pair now works at assigned addresses on EP0. Firmware reset
  and deferred SET_ADDRESS pass, but reset during active TX is unverified.
  Selected descriptor/configuration/enumeration and descriptor DATA toggles now
  pass on the model; general requests/STALL/NAK and full status retry service
  remain absent. Duplicate write DATA1 is suppressed only while that
  control pair's write status is pending. General STALL/NAK behavior is absent.
  The selected TUSB1106 interface and Ethernet SNI integration have no board proof.
- The frontier 1024×18/eight-register core is an isolated model, not supported
  ASIC RTL. Core-only unmapped synthesis grows from 5,647 to 40,452 generic cells;
  the program array grows from 2,048 to 18,432 enabled flip-flops. Production
  storage, encoding/capability and physical-flow decisions are pending.
  The call model adds 58 unmapped generic cells and ten return-address flops;
  packet timing now passes in simulation, with no physical or full-USB proof.
  Generic carry adds another 35 cells and reduces the receiver to 310 words;
  the 403-word OUT and 629-word bidirectional images still cannot run on the
  production core. Preparing TX before tokens adds no new RTL or instruction.
  The 648-word live TX and 776-word control images add no RTL/ISA feature either;
  their execution/storage and physical-fit assumptions remain model-only.
  The enumeration image uses 1,012 words, leaving 12 in the model. Its selected
  enumeration sequence and finite service do not establish full USB compliance.
- The 128x16 program memory and runtime storage map to standard cells and may be too small for complex
  USB, CAN, or Ethernet firmware. The current design uses 79.15% of its allocation;
  larger buffers/programs or more execution contexts require a new area budget.
- Sustained 10 Mbit Ethernet remains unsupported. The planned SNI experiment
  allows only five 50 MHz core clocks per serial bit. A larger-program model
  now passes bounded minimum-frame capture/TX and offline FCS tests, but cannot
  receive continuously while processing results. The actual 128-word core
  cannot load the image. RX data/skew/duty limits, carrier tail behavior,
  TX clock-loss timeout and physical board timing remain open; generic timed
  I/O, storage, higher-throughput execution or concurrency may be required.
- Runtime v1 supports one fully buffered request of at most 64 input/output
  entries. Streaming, mid-request parameter changes, cancellation, and
  concurrency needed for continuous full-duplex traffic remain unimplemented.
  The generic dispatcher uses all 128 instruction words. Fixed-function
  protocol engines remain outside the project architecture.
- KLayout DRC, layout XOR, and EQY equivalence are disabled in the current flow.
- The current routed metrics report 438 maximum-fanout violations;
  423 are clock-buffer outputs and 15 are signal-buffer outputs. Review clock
  clustering and signal buffering against the library limits before physical
  signoff; passing timing/slew does not resolve this constraint.
- Runtime PnR/signoff SDC now specifies the asynchronous request exception and
  held-data settling bound, retaining the pinned 20 ns clock and 4 ns I/O delays.
  Board-specific timing/CDC/MTBF signoff remains open.
  The historical baseline used fallback SDC.
- Power and IR-drop values are preliminary because realistic activity vectors
  and explicit voltage-source locations were not supplied.
- No FPGA or fabricated-silicon interoperability testing has been performed.
- The development-container template still uses `ihp-sg13g2` and LibreLane
  `3.0.0.dev44`; use the pinned local CMOS5L flow in
  [docs/physical_flow.md](docs/physical_flow.md) for physical builds.

## Environment

Ruff is included in the locked development dependencies for Python linting.

Python 3.12 and all Python dependencies are managed by
[uv](https://docs.astral.sh/uv/). Install either Icarus Verilog or Verilator as
the RTL simulator, then initialize the locked environment:

```sh
uv sync --locked
```

Do not install the test dependencies with `pip`; update them with `uv add
--dev` so `pyproject.toml` and `uv.lock` remain synchronized.

Format Python code with Ruff:

```sh
uv run ruff format .
```

## Run the RTL simulation

Icarus Verilog is the default simulator:

```sh
uv run make -C test
```

To use Verilator instead:

```sh
uv run make -C test SIM=verilator
```

Run the instruction-model, assembler and runtime unit tests, and type-check
the instruction model, separately:

```sh
uv run pytest test/test_assembler.py test/test_isa.py test/test_program.py test/test_isa_golden.py test/test_isa_sync.py test/test_runtime_units.py test/test_runtime_driver.py
uv run pyright
```

After an intentional encoding change, regenerate the golden snapshot with
`uv run python -m tools.snapshot_isa` and the design-document encoding table
with `uv run python -m tools.isa --doc`.

The default Icarus test produces `test/tb.fst`, which can be opened with
GTKWave or Surfer.

## Run the CMOS5L physical-design flow

The pinned Tiny Tapeout support tools, LibreLane version, and IHP CMOS5L PDK
are installed locally under this project rather than system-wide. See
[docs/physical_flow.md](docs/physical_flow.md) for installation, activation,
hardening, and report commands. Use that flow to measure mapped cell area,
placement utilization, routing, and timing for the 6x4 allocation. The latest
routed runtime build fits at 79.15% utilization with clean routing/Magic DRC and
LVS, positive setup/hold slack in all three corners, and passing mapped tests.
The measured results and remaining signoff caveats are recorded there.

## Project layout

- `src/`: synthesizable Verilog and the LibreLane configuration
- `firmware/`: protocol examples and generic runtime dispatcher
- `tools/`: assembler, instruction encoder, and controller ABI library
- `test/`: cocotb testbench and simulator Makefile
- `docs/runtime.md`: current architecture, ISA extensions, and runtime ABI
- `docs/design.md`: baseline architecture and verification report
- `docs/physical_flow.md`: pinned local CMOS5L toolchain and hardening workflow
- `info.yaml`: project metadata, pinout, sources, and 6x4 tile allocation
- `.github/workflows/`: RTL tests, GDS build, precheck, and documentation jobs

## Assemble firmware

```sh
uv run python tools/assembler.py firmware/uart_tx.asm
```

See [docs/runtime.md](docs/runtime.md) for the current runtime ISA and ABI, and
[docs/design.md](docs/design.md) for the baseline instruction set/design report.
