> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN frame-ending and overload exploration

2026-10-25. New independent wire tests reproduce three gaps in the frozen
1,024-word image: a dominant last EOF bit discards a valid received frame;
first-intermission dominance does not generate an overload flag; third-bit
intermission SOF discards the preceding frame. The ordinary-frame control
passes for payload lengths0,1 and8. No tail fix is claimed as working yet.

## Wire cases and scope

The [peer](../study/protocol_exploration/can_tail_peer.py) constructs frames with
independent polynomial-division CRC and stuffing, then changes exactly one tail
bit. It checks the public transceiver TXD/RXD boundary, runtime data/status and
counter queries. It neither reads private counters nor uses the instruction
trace for expected protocol behavior.

- Last EOF: accept the valid received data, maintain the normal ACK and avoid
  an error flag/counter charge. The intended payload sweep is0,1,8, but the old
  image stops at its first counterexample; later sweep cases are not proven.
- First/second intermission: generate a six-dominant-bit overload flag at the
  following bit, an eight-recessive-bit delimiter and intermission, preserving
  the received data and counters. The old image stops at the first missing
  flag, so second-intermission coverage is planned rather than passed.
- Third intermission: classify a dominant bit as next-frame SOF and preserve
  the completed frame. The peer sends a complete successor and explicitly
  observes its missing ACK while the one-frame runtime capture completes.
  This case does **not** prove continuous reception or successor-frame service.
- Control: repeated ordinary receive exchanges with arbitrary data through8
  bytes, correct output/status and unchanged counters, without reload/reset.

The earlier counter regression deliberately expected local17 for these tail
cases. It remains frozen as evidence of the former restricted profile; that
assertion must not become the acceptance oracle for new legal-tail behavior.

```sh
# Expected failure:3 tail gaps,1 ordinary-frame control passes.
uv run --locked python study/protocol_exploration/run_can_tail.py can_tail --expanded-model --prior-monitor
# Both expected to reject the draft before simulation:
uv run --locked python study/protocol_exploration/run_can_tail.py can_tail
uv run --locked python study/protocol_exploration/run_can_tail.py can_tail --expanded-model
uv run --locked pytest -q test/test_can_tail_units.py
```

## Retained firmware attempt and measured limit

The [builder](../study/protocol_exploration/build_can_tail.py) produces a separate
[1,067-word draft](../study/protocol_exploration/can_tail_candidate.asm),43 words
above the real1,024-word generic assembler limit and939 above production128.
The original passing image and its regressions are unchanged. This is an
actual capacity failure; it is **not** an executed timing result or proof that
all firmware solutions require that size.

The draft separates ACK delimiter/first six EOF checks, the ignored receiver
last-EOF polarity, and intermission classification. It proposes bounded RX
service with at most two generated overload flags, delimiter sampling with a
32-sample budget and an eighth-delimiter-dominance path. Protocol work remains
generic instructions; no RTL/opcode/storage feature or new RAM byte is added.

The draft has **no behavioral proof**. Its pads, counter/flag semantics, receive
data preservation, repeated overloads, passive-node behavior and older error/
phase/winner/retry regressions must be executed after it fits an experiment
model. TX tail service is unchanged. Overload-flag bit-error/prolonged-dominance
counter rules are not implemented in this first draft. Delimiter form-error
handling remains incomplete; a bounded wait must not be mistaken for full CAN
recovery. Continuous-node capture, request/reset handling and hardware/physical
verification remain open.

The [machine record](can_tail_results.json) preserves exact negative XML/source
hashes, both capacity diagnostics,56 project units and unchanged physical-source
fingerprints. The new unit checks source freshness and actual size diagnostics,
not protocol correctness. CI includes that unit; expected-negative simulation
is kept separate from passing suites.

**Next task goal:** make the measured tail workload executable: attempt further
generic firmware compaction or prototype larger generic instruction addressing,
then run the independent tail peer and retained CAN regressions. Compare storage/
encoding/cycle costs and unmapped synthesis if the model architecture changes.
Do not add a CAN-specific engine. Preserve this first draft and wire failures.

Reference: [Bosch CAN2.0](https://tech-tools.com/files/can2spec.pdf), Part A9.1
and Part B3.2.4/7.1: the modern EOF/intermission distinctions and overload timing.
