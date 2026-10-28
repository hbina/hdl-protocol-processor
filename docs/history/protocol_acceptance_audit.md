> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Nine-protocol acceptance audit

2026-10-25. The original exploration goal remains **open**. All nine protocols
have concrete firmware/peer experiments, and selected bidirectional exchanges
now pass for each on production RTL or an explicitly larger generic model.
That does not close every acceptance requirement in the original
[plan](protocol_exploration.md). UART's specified runtime ABI now passes on a
251-word/eight-register model; production capacity still blocks its deployment.
JTAG invalid-length handling now passes on a198-word/four-register model.
CAN's [701-word follow-up](can_ack_recovery_study.md) passes missing-ACK
active flags and bounded retry tests; the [811-word candidate](can_winner_study.md)
now receives/ACKs arbitration winners and retries a retained payload. The
[819-word candidate](can_resync_study.md) adds bounded RX falling-edge phase
correction, preserving a fixed-clock missing-ACK failure. The
[1,020-word call-model candidate](can_fault_state_study.md) now supplies persistent
counters, selected active/passive TX flags and bus-off/isolation/recovery.
The [1,021-word follow-up](can_receive_flags_study.md) adds timed RX CRC/stuff/
selected form-error flags after a48-word firmware compaction. The
[1,023-word follow-up](can_postflag_study.md) adds receiver first-post-flag+8
and repeated prolonged-dominant+8 accounting; five more groups pass. The
[1,024-word compact image](can_flag_compact_study.md) now adds selected RX/TX
active-flag bit-error counters/restarts: five fault groups, five earlier
post-flag groups and two selected RX groups pass, with no new RTL/ISA/RAM.
The [tail investigation](can_tail_study.md) now reproduces three wire gaps and
one ordinary-frame control; its1,067-word RX draft exceeds model capacity and
has no behavioral proof. A separate [compact tail candidate](can_tail_compact_study.md)
now fits 1,024 words and freshly passes seven selected RX-tail groups.
Broader CAN
node recovery remains unfinished: missing implementations/tests are not
reproduced architectural impossibilities.

## Evidence actually checked

`uv run --locked python tools/audit_exploration.py --output docs/protocol_acceptance_results.json`
checks source fingerprints, saved XML fingerprints, clean test counts and exact
case names for seventeen passing source-bound records spanning nine protocols. It also
executes all seventeen production-capacity failure commands again and verifies the
seven historical physical-source hashes. Those checks passed in the recorded snapshot. Source formatting and regenerated
XML now differ from some saved fingerprints; the audit rejects the current
checkout. Retained results are historical evidence, not a fresh provenance
check. See [pre-commit verification](commit_verification.json) for fresh tests.
The [machine record](protocol_acceptance_results.json) preserves the commands,
hashes and outcomes. This is an integrity/capacity audit, not another protocol
simulation run or a protocol-compliance validator.

The tool requires the original XML/generated-model artifacts associated with
the referenced JSON records. A fresh checkout must restore those artifacts,
or rerun the experiments and refresh their source-bound evidence snapshots;
new XML wall-time values will not match an old XML digest. The checker rejects
that mismatch rather than treating unrelated results as historical evidence.
It is intentionally not added as a default CI step that depends on untracked
historical build products. Existing CI runs the actual experiment regressions.

| Protocol | Current measured exchange | Record checked | Remaining acceptance work / reproduced blocker |
|---|---|---|---|
| UART |107-word production probe;251-word generic model now validates TX/RX/TX_THEN_RX, software clock deadlines, framing/phase/rate/drain/reset/recovery | Production3 UART cases plus6 new runtime model groups | Fresh production failure251>128; the full model candidate uses eight registers and is not mapped/board verified |
| SPI | 72 words, production core; mode0 simultaneous multi-byte TX/RX through64 bytes, CS/clock/data checks | Same record includes1 SPI case | Valid envelopes only; request validation, configurable modes/timing and mapped/board checks remain open; modes1–3 are later scope |
| I2C | 249 words,256-word model; write/read, repeated START, ACK/NACK, stretching and bus-clear recovery |5 model cases | Fresh production assembly fails249>128; generic code density/storage is a candidate fix; invalid-envelope and board/electrical coverage remain open |
| JTAG |125-word production probe plus198-word validated candidate on the256-word model; TAP reset, IR/DR, non-byte-aligned scans1–512 bits and rejection/recovery | Production1 case plus2 new model groups | Fresh production failure198>128;30 rejected requests preserve pins/TAP and drain input; mapped/board coverage remains open |
| SWD | 230 words,256-word model; DP reads/writes, parity, turnaround, bounded WAIT and FAULT/ABORT recovery |2 model cases | Fresh production failure230>128; selected target already in SWD mode; full request validation, AP/multidrop/selection variants and board checks remain open |
| PS/2 | 188 words,256-word model; host command/link ACK, device response and receive bursts, parity/timeout recovery |2 model cases | Fresh production failure188>128; valid envelopes only, actual device/voltage/clock-envelope coverage remains limited |
| CAN | Generic call model:1,024-word TX/RX/winner/retry, timed selected RX/TX flags/bit-error restarts, selected post-flag counters and bus-off/recovery; selected valid-frame drift/step tests |3 frozen focused cases plus3 each ACK/winner/phase groups,5 fault-state,5 RX-flag,5 post-flag and5 compact flag-bit groups plus5 post-flag regressions | Fresh production failures622/701/811/819/1020/1021/1023/1076/1024/1067>128;1,067-word RX-tail draft exceeds model capacity and is unverified;1,076-word draft fits after52-word compaction to1,024;1,069-/1,034-/1,028-word attempts exceed model capacity; active-flag RX/TX counter, old-counter, missing-flag, fixed-clock and passive-flag failures preserved; remaining counter/timing/EOF/overload/busy-bus rules remain open |
| USB |1,012 words, generic CALL/carry model; selected enumeration, descriptor chunk toggles/retries, configuration and arbitrary EP0 vendor write/readback |10 model cases | Fresh production failure1012>128; finite service, selected requests only, vendor command payloads1–8 after enumeration;0-byte packets pass separate packet probes but zero-byte vendor commands are not covered by the enum image |
| Ethernet |280 words,512-word model; minimum-frame10 Mbit/s SNI TX/RX and firmware FCS, timing/error checks |6 model cases | Fresh production failure280>128; buffered minimum frames only, RX tests cover nominal/−100ppm rather than general skew/duty/oscillator tolerance; no sustained reception or real-PHY proof |

All peers are independent of the firmware instruction trace for expected data.
The firmware supplies framing/parity/CRC/stuffing where required. Electrical
ownership is checked at the documented digital boundaries; external CAN/USB
transceivers and Ethernet PHY do not provide a protocol controller/MAC.
Detailed ABI, memory, timing and external-component descriptions remain in the
individual studies linked from the README.

## Requirement-by-requirement conclusion

| Original requirement | Current conclusion |
|---|---|
| Specify nine roles/rates/transactions/interfaces/verification budgets | Present in the plan, resource table, budget artifacts and individual studies |
| Arbitrary runtime payloads/parameters and received results/status | Demonstrated for selected valid envelopes; USB enum uses independent USB-host payload and returns it through runtime; standalone IN probe also takes runtime-host TX data |
| Repeated successes/failures without reset/reload | Covered in selected peer tests, including cross-mode CAN and USB control sequences; does not imply missing retry/state behavior works |
| UART first milestone named firmware/test artifacts and exact ABI | `test/test_uart_runtime.py` and the251-word study candidate now pass six groups; `firmware/uart_runtime.asm` is deferred because production assembly fails. The107-word probe remains a separate baseline |
| Relevant failure cases | UART includes28 malformed requests and reset tests; JTAG includes30 pin-stable rejections; CAN now includes timed RX CRC/stuff/form flags, counter/passive/saturation/bus-off/recovery checks; remaining counter and full timing rules stay open |
| Preserve failing attempts and propose generic fixes | Seventeen production-size failures freshly reproduced; CAN1,069-word RX-flag candidate fits after48-word generic-firmware compaction; missing-flag/inlining/passive-flag/drift and USB buffered/short-gap failures remain preserved |
| Measured program/cycle/memory/host budgets | Available, with estimates distinguished from executed results; remaining complete-node/request costs are not yet measured |
| Protocol-independent architectural changes only | Production core remains generic; isolated studies add address/register width, leaf calls and carry operations; no protocol RTL engines/CRC units introduced |
| Regression and physical evidence after architecture changes | Model/legacy regressions and core-only unmapped synthesis exist; production physical source hashes are unchanged. No expanded-core mapped/tile-fit proof |
| Documentation/status | README and detailed source-bound studies exist; this audit updates priority and preserves limitations |
| Reviewable commits | Outstanding: the worktree contains the production foundation and all exploration changes without reviewable project commits; do not equate files/tests with committed baselines |
| Hardware interoperability | Unverified and distinct from functional/physical evidence; not silently inferred from simulation |

The original success alternative permits a reproduced blocker for a concrete
attempt. The seventeen production size failures meet that description for those
images. They do not justify calling unimplemented CAN acceptance
behavior a reproduced blocker, nor prove that every firmware implementation
requires the same size. Further firmware solutions remain worth attempting.

## Generic architecture priorities

1. **Preserve the completed UART model contract and its production blocker.**
   The [251-word runtime study](uart_runtime_study.md) now passes validation,
   software-clock windows, line faults, false-start storms and reset/reload.
   No timer RTL was needed. Production compaction/storage and mapped/board
   evidence remain open; the original107-word image remains frozen.
2. **Complete the remaining CAN functional discriminators.** The
   [198-word JTAG study](jtag_runtime_study.md) now supplies invalid-shape/length
   rejection with TAP preservation. CAN now has ACK-error active flags and
   bounded retries in a701-word candidate, and winner reception/ACK with
   retained-payload retry in an811-word candidate; three peer groups pass for
   each. The819-word candidate now supplies bounded RX phase correction, with
   three peer groups and the fixed-clock negative comparison. The1,020-word
   candidate adds five fault-state groups and selected counters/passive/bus-off/
   recovery rules. The1,021-word follow-up adds five RX-flag/compaction groups.
   The1,023-word candidate adds five post-flag counter groups, preserving the
   old REC1-versus9 failure. An independent transceiver-fault peer now
   reproduces active-flag counter gaps: REC1-versus9 and TEC8-versus16.
   The [draft integration](can_flag_bit_study.md) needs1,076 words and fails the
   real1,024-word model before execution. A separate1,024-word compact image
   now passes the five fault/restart groups, five post-flag groups and two
   selected RX groups; the original draft and counter failures stay preserved.
   The tail peer now supplies three failures plus an ordinary-frame control.
   Its1,067-word draft exceeds1,024 before execution; RX-only overload service
   still needs behavioral proof, and TX tail handling is unchanged.
   Full SJW/TX timing remains open. Do not substitute a size error for
   attempting missing behavior.
3. **Select generic storage/execution from the full measured workload.** Current
   instruction needs span72–1076 words (the1,076-word draft is unverified), including the251-word UART contract image. The wider model uses18,432 enabled program
   flip-flops versus2,048 in production; core-only generic cell count grew from
   5,647 to40,545 with calls/carry. These are not mapped area numbers. SRAM is a
   candidate, but synchronous fetch latency must be included in every critical
   path (USB33/33/34 clocks per bit and Ethernet five clocks per bit).
4. **Revalidate the complete architecture at a physical checkpoint.** Keep the
   historical50 MHz/79.15%-utilized physical design and438 fanout violations
   attributable to their source hashes. Test the selected storage/encoding/host
   capabilities and rerun mapped timing/fit before claiming ASIC support.

**Next task goal:** make the measured1,067-word RX tail workload executable
through further generic firmware compaction or larger generic instruction
addressing. Run its independent tail peer and retained CAN regressions, and
measure storage/encoding/cycle cost and synthesis if architecture changes.
No words remain in the last passing1,024-word image. TX tail and overload-flag
fault rules remain open; a size error does not verify the draft. Keep the earlier comparisons; model results do not
establish ASIC fit or complete CAN timing/confinement.
Keep protocol decisions in firmware, preserve old tests and any minimized failing
attempt, and measure code/cycle/storage costs before changing generic hardware.
The full nine-protocol acceptance goal remains open.
