> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# I2C TX/RX: program-capacity experiment

Date: 2026-10-24. **The current 128-word ASIC cannot load this candidate.**
The candidate uses 249 words. An isolated 256-word RTL model exercises its
behavior; it does not establish that a larger ASIC closes timing or fits the
tile allocation. Production RTL, the production assembler's limit, and the
physical baseline remain unchanged.

This is a reproduced blocker for this firmware implementation, not a proof
that every possible bidirectional I2C program requires more than 128 words.
The original address-write example still works on the actual core. The full
[nine-protocol exploration](protocol_exploration.md) remains active.

## Firmware behavior

[The candidate](../study/protocol_exploration/i2c_candidate.asm) implements a
single-controller, seven-bit-addressed I2C transaction entirely with generic
instructions. It drives SCL/SDA low or releases them using output enables;
there is no protocol-specific hardware or host-precomputed bus waveform.

1. Wait for an idle bus, then generate START and the write address.
2. Transmit 1..64 runtime input bytes, sampling target ACK after every byte.
   In the register-target example, the first byte is the register pointer and
   subsequent bytes are write data. The firmware treats them as arbitrary data.
3. If receive_count is nonzero, generate repeated START and the read address.
4. Receive 1..64 bytes, ACK intermediate bytes, NACK the final byte.
5. Generate STOP, release both pins, and publish a matching runtime completion.

The same image handles repeated write/read requests without reset or reload.
The host uses the existing transport/queues to provide parameters and payload
and retrieve output. Incoming bytes are independently supplied by a target
model rather than derived from the firmware instruction trace.

### Valid-request ABI

```python
request = Request(
    request_id,
    1,
    arguments_length=2,
    input_count=len(payload),
    output_limit=receive_count,
)
await controller.submit(request, payload, bytes([address7, receive_count]))
output, completion = await controller.complete(request)
```

Parameters start at address zero: byte 0 is the seven-bit address; byte 1 is
receive_count, 0..64. Input payload length is 1..64, including the register
pointer when the target uses one. A write-only request has receive_count zero;
a register read submits the register pointer as its one-byte payload and
requests readback. Combined write-then-read is also possible; the target's
pointer semantics determine the read location after writes.

The image consumes the full submission but does not validate its operation,
flags, reserved fields, argument layout or declared limits. The caller must
provide initialized parameters and a valid envelope with sufficient output
capacity. These validation gaps are shared with the compact UART/SPI probes
and remain outside the passing evidence.

Output entries have zero metadata. Completion status 0 means OK; 8 means
target NACK; 9 means bus/clock timeout or a recovery-only request. Input count
includes discarded bytes after an error. Output count is the number of valid
received bytes published before failure. Request ID is returned unchanged;
detail and event reserved fields are zero. Transport error code meanings do
not change: these statuses are firmware result codes.

### Timing and interface

uio4 is SCL, uio5 is SDA; other output enables stay zero. The output latch is
zero throughout. An actual board needs correctly sized pull-ups and voltage
compatibility; this study uses ideal digital wired-AND resolution and has no
pad, rise/fall-time, board or interoperability signoff.

At the modeled 50 MHz core clock, nominal half-cycle waits are 250 clocks
(5 microseconds), with additional instruction/polling overhead. Consequently
the unstretched bus runs below 100 kHz, with inter-byte gaps. The independent
peer checks a minimum SCL period of 10 microseconds, low period 4.7 microseconds,
high period 4 microseconds, START hold and STOP setup of 4 microseconds. These
limits come from [NXP UM10204, Table 11](https://cache.nxp.com/docs/en/user-guide/UM10204.pdf).
This is partial digital timing coverage, not full I2C electrical compliance.

The candidate samples synchronized SCL before progressing after release.
Per-clock low polling is bounded to 256 attempts, approximately 20.48
microseconds plus synchronization and control overhead. It tolerates the
tested 8-microsecond stretches, but does not support an indefinitely stretching
target. Initial busy-bus polling is approximately 25.6 microseconds.

### Error handling and lessons from the peer

A NACK drains any remaining input and attempts STOP. An in-flight clock
timeout releases the controller pins, drains input, and allows approximately
1.33 milliseconds for SCL to recover. If SCL recovers, firmware issues nine
bus-clear clocks followed by STOP before retiring the failed request.
Bus-clear pulses have fixed waits; this study does not establish interoperability
with targets that repeatedly stretch during bus clear itself.

The first implementation only released pins after timeout. A peer holding
SDA low during ACK exposed that a subsequent request could not start. The
bounded recovery sequence fixes that tested failure. The peer also exposed
a too-short first recovery high period; an explicit high wait fixed it.
These are protocol/firmware failures, separate from physical timing closure.

If SCL stays low throughout recovery, firmware returns TIMEOUT with pins
released and remembers unfinished recovery in scratch memory. The permanent
clock-fault tests bound completion to less than 2 milliseconds including
host interaction. While SCL remains low, further requests fail with the bus
released. Once SCL recovers, a target may still hold SDA during ACK: the first
retry can be consumed solely to clear that old transfer and report TIMEOUT;
the following request performs the new transaction. Firmware does not silently
replay a request during this recovery-only path.

Successful STOP clears the recovery flag. An initially busy bus without an
unfinished transfer is left released and reports TIMEOUT, rather than issuing
recovery clocks. Multiple controllers/arbitration are not supported. Writes
before an error, and traffic generated during bus clear, can affect target
state; errors do not promise rollback or exactly-once peripheral effects.

## Resource evidence and next architectural decision

| Resource | Measured or inspected result |
|---|---|
| Assembled candidate | 249 words; actual assembler rejects it at the 128-word limit |
| Over capacity | 121 words beyond actual hardware capacity |
| Expanded model | 256 words; seven spare words in this candidate |
| Scratch | 20 allocated bytes at 144..163: 16-byte event plus TX/RX counts, recovery flag and saved bit count |
| Registers | All four 8-bit registers used; bit-loop counters spill to scratch during SCL timeout polling |
| Queues | Existing 64-byte input and 64-entry output; one request at a time |
| Physical cost of expansion | Unmeasured; doubling memory adds 2048 instruction-storage bits plus addressing/decoder changes |

The straight-line candidate initially used 215 words. Broader recovery tests
increased it to 249. It already shares the transmitted-byte loop across the
write address, payload and read address. Separate clock polling paths for
data, ACK, repeated START, receive ACK and STOP contribute to code size.
Dropping these paths is not treated as completing the same experiment.

Next generic options are software code-density improvements, reusable
control-flow facilities, or larger instruction storage. No option is selected
as a production architectural change yet. A 256-word implementation would also
need to represent its capacity in the host ABI: the current program_words
capability occupies one byte. The study intentionally leaves that hardware
register reporting 128 and must not be used as a board configuration.

The 256-word model changes only a generated copy of instruction memory depth,
PC width, loader cursor width and long branch target width. All other RTL is
the production source. The production assembler is imported as a separate
module for this study with its limit set to 256; its normal 128-word behavior
is untouched. Generated substitutions are checked against exact source text
so a later core change requires an explicit audit of this experiment.

Neither this result nor the historical 50 MHz timing establishes physical
fit for 256 words. Any production extension needs updated capability encoding,
regressions, synthesis area feedback and a fresh mapped/physical checkpoint.
The existing fanout, CDC, pad and power signoff caveats remain open.

## Reproduction and verification

Run from the repository root with the locked environment and Icarus installed.
The same temporary Icarus setup as [the earlier probes](protocol_probe_results.md)
was used locally; no new Python dependency is required.

Actual hardware capacity, **expected exit code 1**:

```sh
uv run --locked python study/protocol_exploration/run_i2c.py
```

Expected diagnostic: `Actual ASIC capacity: program contains 249 words; maximum is 128`.
This failed assembly is the current reproducible blocker.

Explicit expanded-model test:

```sh
uv run --locked python study/protocol_exploration/run_i2c.py --expanded-model
```

Five tests in [the independent peer](../study/protocol_exploration/i2c_peer.py)
exercise the modeled public pins and runtime interface:

- Arbitrary multi-byte register writes/readback, input through 64 bytes,
  output through 64 bytes, repeated START, intermediate ACK and final NACK.
- Address, data and read-address NACK, 8-microsecond clock stretching at seven
  transfer positions, and subsequent successful requests.
- Longer clock stalls at seven positions across TX, ACK, repeated START, RX
  and STOP; preserved partial output and recovery without reset/reload.
- Permanent clock faults during data and ACK, bounded completion, quiet busy
  retries, recovery-only retry and a subsequent successful request.
- Initially stuck SDA and SCL, released controller pins and post-fault recovery.

An event-driven resolver combines controller output enables, target drive and
fault injection; neither participant can force a resolved high against a low
driver. The peer has its own address, ACK, register-pointer and byte state.
Its timing checks observe resolved edges, including recovery clocks.

The [evidence record](i2c_capacity_results.json) stores actual results, source
hashes and the assembly failure. The runner rejects missing/failed results
and source changes during execution. Generated model and simulator results
live under `test/sim_build/i2c_capacity256/`. CI runs this as a separate,
explicitly named capacity experiment; the production-RTL suite now contains ten
tests. There is no mapped or hardware test evidence for this candidate.
