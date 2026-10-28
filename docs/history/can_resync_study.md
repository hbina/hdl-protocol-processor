> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN receive phase correction in generic firmware

2026-10-25. An **819-word candidate** now follows falling edges during CAN
reception using ordinary GPIO reads, counters, branches and waits. Three model
groups and all49 unit tests pass. The frozen811-word candidate fails the same
valid frame at +5,000 ppm, with no ACK. Production rejects819>128. No RTL,
instruction, timer, edge-capture hardware, register or data memory is added.

The [builder](../study/protocol_exploration/build_can_resync.py) extends the
[winner-reception firmware](can_winner_study.md), preserving that comparison.
The [candidate](../study/protocol_exploration/can_resync_candidate.asm) runs on
the same isolated1024×18/eight-register model. The [result snapshot](can_resync_results.json)
contains source/XML hashes for the positive and negative runs, timing traces,
unit commands, real production-capacity rejection and unchanged physical hashes.

This is **bounded RX phase correction**, not a full implementation or proof of
CAN bit synchronization. TX still uses a fixed nominal clock. Late edges beyond
the observation window, general synchronization-jump-width rules and a full
transceiver/oscillator/propagation budget remain open.

## Reproduced failure and firmware change

The prior receiver samples near75% and follows a fixed400-clock schedule after
SOF. With a +5,000 ppm independent transmitter and the test eight-byte frame,
the DUT never drives ACK at wire bit108. The negative XML records that public
pin failure; it is not a deliberately failing assertion about the implementation.
The peer's valid frame/CRC comes from independent polynomial division.

The receive loop needs143 clocks of balanced bit/stuff/header/CRC processing.
At75%, only100 clocks remain before the next nominal bit boundary, so that work
overlaps the edge. The new firmware moves RX sampling toward50%, leaving200
clocks before the next boundary. It then uses part of the existing wait budget
to observe falling edges:

- If the previous sample was dominant, keep the400-clock period. That sample
  cannot qualify a recessive-to-dominant synchronization edge.
- If the previous sample was recessive, poll27 times,4 clocks apart, at offsets
  148–252 from the sample. A detected dominant value adjusts the next sample to
  200 clocks after that observation. Only the first qualifying edge is used.
- With no observed edge, retain the400-clock period. Detection yields an
  interval348–452 clocks, so correction is bounded to52 clocks/1.04 µs.

The two-flop input synchronizer and polling quantize edge observation; the
firmware does not know an exact analog arrival time. Earlier edges may first
be observed at the window's start. An edge later than the window does not
receive the full CAN-required clipped correction. This is an explicit limit,
not an implemented configurable SJW facility.

ACK timing changes with the sample point: drive/release at200 clocks after
the CRC-delimiter/ACK sample respectively, keeping a400-clock dominant pulse.
The arbitration-loss handoff now reaches the next RX sample300 clocks after
the75% TX sample, aligning with the next bit's50% point. Stuff/CRC decoding,
winner ACK/output, packed payload preservation and the shared retry cap remain
in firmware. r4/r7 are reused during RX after the prefix CRC has been handed
to r2/r3; TX resets its mirrored CRC before reuse.

## Measured scope and resources

| Item | Evidence |
|---|---|
| Program |819 words,8 above the winner candidate;205 free model words |
| Execution |50 MHz modeled core;125 kbit/s nominal CAN,400 clocks/bit |
| RX phase/period |45.188–56.105% of peer cells;372–436 clocks between observed samples across13 recorded exchanges |
| Clock mismatch | −5,000/0/+5,000 ppm on an eight-byte regression vector; selected length/phase cases at ±5,000 ppm |
| Phase steps | Alternating0/400 ns persistent offsets at selected falling edges in payload/CRC region, combined with drift |
| Start phase |1/5/10/15/19 ns across selected length cases; not the full Cartesian product |
| Payloads | DLC0–8; runtime identifiers/data, all-zero/one and selected patterns |
| RAM/registers | Existing128–254 private footprint and eight model registers; no added storage |
| ACK | One400-clock/8 µs dominant pulse on valid frames; no ACK for injected bad CRC |
| External boundary | uio0=TXD, uio1=RXD; external transceiver and terminated CAN bus, no external controller |
| Physical | Historical production hashes unchanged; no larger-core area/timing or board proof |

The measured intervals on both sides of400 demonstrate actual phase adjustment,
not only a change to the initial sample point. An internal execution observer
records sample times; it never generates expected data or steers the peer. Its
timestamps are compared against the peer's independently generated cell boundaries,
and every successful sample must lie inside its corresponding physical cell.

## Tests and reproduction

```sh
uv run --locked pytest -q test/test_can_resync_units.py
# Expected exit1:819 words exceeds production128.
uv run --locked python study/protocol_exploration/run_can_resync.py can_resync
uv run --locked python study/protocol_exploration/run_can_resync.py can_resync --expanded-model

# Expected exit1: retained811-word fixed-clock image misses ACK at +5,000 ppm.
uv run --locked python study/protocol_exploration/run_can_resync.py can_resync --expanded-model --fixed-clock --test-filter test_clock_drift_regression
```

Positive and negative builds have separate directories, so reproducing the
failure does not overwrite passing XML. The runner saves provenance even for
the failed comparison. It still exits nonzero on failures or unexpected skipped
coverage and checks
source hashes before saving results.

Three positive groups cover:

- The same eight-byte frame at +5,000/−5,000/0 ppm, checking decoded data, counts,
  ACK and measured sample placement.
- DLC0–8 with phase steps, five selected start phases and ±5,000 ppm; bad CRC
  with no ACK, then a successful request without reset/reload.
- Existing TX/RX, two successive arbitration winners with retained-payload
  retry, and arbitration loss followed by missing ACK and third-attempt success.

The source/capacity unit checks deterministic generation and production
rejection. CI runs the three positive groups separately and uploads their XML,
evidence and timing records. The negative comparison has the explicit manual
reproduction command above. The default production regression is unchanged.

## Remaining acceptance work

This does not establish full CAN resynchronization/SJW behavior, TX phase
correction, general edge-glitch filtering or immunity to arbitrarily large
phase steps. Nor does it implement broader error flags, persistent error
counters, error-passive/bus-off or overload handling. Invalid received frames
still return local statuses. Continuous multi-node reception remains unavailable
while decoding output/rebuilding TX, and full request/reset coverage is absent.

Production capacity/encoding/storage, physical timing/area, real transceiver
delay and board interoperability remain unresolved. Historical fanout/signoff
limitations remain. The next functional task is to attempt persistent CAN error
state and error-passive/bus-off behavior, keeping every decision in generic
firmware and measuring any storage/execution blocker.

Reference: [Bosch CAN2.0 specification](https://tech-tools.com/files/can2spec.pdf),
Part A section8, for synchronization qualification, phase error and bounded jump
width. The selected polling experiment exercises part of that behavior; it is
not a complete normative implementation.
