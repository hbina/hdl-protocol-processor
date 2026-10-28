> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Generic ISA frontier: program capacity and register pressure

Follow-up: the [live USB study](usb_live_study.md) now adds generic leaf CALL/RET
in another isolated model and meets packet response timing. The frontier model
and measurements in this document remain frozen comparison evidence.

2026-10-25. This is an isolated architecture experiment, not a new supported
ASIC configuration. Production RTL, assembler, 128-word program store and four
registers remain unchanged. The experiment has no protocol-specific opcodes,
engines, modes or CRC hardware.

The [USB study](usb_receive_study.md) reproduced a response-time failure after
trying a firmware-only optimization. Its compact buffered decoder still spends
about 92 µs decoding and 33 µs calculating CRC after an eight-byte packet ends.
The [combined CAN candidate](can_transmit_study.md) separately exceeds the
previous 512-word study capacity with 622 instructions. These motivate testing
more generic registers and more addressable program storage before selecting
a production architecture.

## Concrete model and encoding

[generic_frontier.py](../study/protocol_exploration/generic_frontier.py)
generates a temporary core with 1024 eighteen-bit instruction words, eight
eight-bit registers and a ten-bit PC/loader address. It uses exact checked
source replacements. It never edits `src/` or `tools/assembler.py`.

The low 16 bits retain the existing opcode/suboperation encoding, including
the earlier study's ninth address bit. Two additional bits extend operands:

| Instruction class | Bit 16 | Bit 17 |
|---|---|---|
| Register and immediate operations | Destination register bit 2 | Source register bit 2 when used |
| JZ / DJNZ | Tested/counted register bit 2 | Branch address bit 9 |
| JMP / JFAIL | Zero in emitted code | Branch address bit 9 |
| Operations with no register/address operand | Zero | Zero |

Long branch address bit 8 remains in operand_a[1] for JMP/JFAIL and
operand_a[3] for JZ/DJNZ; the existing long-form selector stays in operand_a[2].
No extra prefix instruction or branch cycle is added. Register-indirect data
addresses remain eight bits; data RAM and the runtime ABI are unchanged.
All eight registers reset on reset/configuration exit. Pending LOAD/PREAD
destinations widen to three bits, so high-register reads commit correctly.

The loader already transfers three six-bit chunks per instruction. The model
stores all 18 received bits; production uses only 16. Existing 16-bit programs
can use the same instruction words and loading sequence on the model. An
eighteen-bit program using the extensions is not supported on production RTL.
The board-visible capabilities still report the production 128-word ABI: this
study does not define a deployable host configuration.

The encoding is an experimental choice, not a commitment. Generic program
banking, subroutines, denser code or another execution organization remain
alternatives. Eight registers are a USB scheduling hypothesis; this study
does not prove they solve USB throughput or justify their exact count.

## Combined CAN execution

[build_can_frontier.py](../study/protocol_exploration/build_can_frontier.py)
copies the previously capacity-only combined source into a clearly labeled
[frontier image](../study/protocol_exploration/can_frontier_candidate.asm).
The 622 instructions are unchanged apart from comments. The old source and
128-/512-word capacity failure records remain frozen and reproducible.

On the larger model, the combined image now executes operation 1=receive and
operation 2=transmit through the same runtime request loop. It alternates TX
and RX without reset, firmware reload or a host-generated line waveform.
The host supplies arbitrary TX ID/data at runtime; an independent simulated
CAN peer supplies RX frames and checks TX with its own CRC/frame encoder.
RX returns identifier/DLC/payload, while TX reports input consumption/status.

The focused model tests cover 0-, 1- and 8-byte exchanges, alternating modes,
missing-TX-ACK followed by successful RX, bad-RX-CRC followed by successful TX,
and arbitration-loss release followed by an explicit receive request. They
check output data/counts and an empty runtime channel after each completion.
This is stronger evidence than two separately loaded probes, while remaining
counterfactual to the production ASIC.

CAN still lacks automatic winner reception after arbitration loss, bounded
retries, within-frame edge resynchronization, error flags/counters and fault
confinement. The peer ACKs the winning transmitter using another simulated
receiver. The DUT does not receive or ACK that winner automatically. Request
shape validation and broader CAN conformance remain incomplete.

## Verification

[frontier_results.json](frontier_results.json) records commands, outcomes and
source hashes. The checks distinguish:

- Three assembler tests: all seven legacy firmware images retain identical
  words; fixed eighteen-bit register/branch encodings; branch-bank boundaries
  and rejection of out-of-range operands.
- A core diagnostic: public-pin loading through word 1023, branch banks around
  256/512/768, high-register conditional branches, memory/peripheral read commit,
  cross-bank register operations, GPIO and reset/reload of high registers.
- Combined CAN alternation and cross-mode recovery on the new model.
- The existing ten UART/SPI/I2C-example/JTAG/runtime RTL tests, separately run
  against the model to check compatibility. This does not replace production
  evidence or add mapped/hardware coverage.

```sh
uv run --locked pytest -q test/test_frontier_assembler.py
uv run --locked python study/protocol_exploration/build_can_frontier.py
uv run --locked python study/protocol_exploration/run_frontier.py can_duplex --expanded-model
uv run --locked python study/protocol_exploration/run_frontier_legacy.py can_duplex --expanded-model

# Expected exit 1: production capacity remains 128 words.
uv run --locked python study/protocol_exploration/run_frontier.py can_duplex
```

## Preliminary storage cost

Paired `synth -top protocol_core -noabc` runs use YoWASP Yosys 0.55, commit
60f126cd0. These are **unmapped generic-cell counts for the core alone**,
not standard-cell area, whole-chip counts, timing, power or tile-fit results.

| Metric | Production core | Frontier model |
|---|---:|---:|
| Generic cells, no ABC | 5,647 | 40,452 |
| Program-storage enabled flip-flops | 2,048 | 18,432 |
| Generic multiplexers | 2,434 | 18,904 |
| Register-file resettable bits | 32 | 64 |

The program array still maps to flip-flops in this diagnostic: nine times the
stored bits, plus a larger read mux. The generic core-cell total grows about
7.16 times. These quantities cannot be compared directly with the README's
mapped ASIC cell/area figures. They demonstrate that simply retaining the
current flop-based program implementation has a substantial cost.

```sh
# Uses the existing optional local YoWASP tool; does not run Tiny Tapeout PnR.
python3 study/protocol_exploration/synth_frontier.py
# Or select an installed compatible yosys executable with --yosys PATH.
```

The synthesis script writes source, scripts, logs and JSON under
`test/sim_build/frontier_synth/`. Final snapshots are retained in the evidence
record. No PDK mapping or physical build was performed for the model. SRAM or
another program-storage implementation needs a separate measured area/timing
budget before production changes. Existing production signoff limitations,
including fanout violations, remain unchanged.

## Next task

Use the extra generic registers to attempt a live USB NRZI/destuff/CRC schedule
and rerun the preserved 4.33 µs response requirement. A larger register file is
not itself a passing timing result. Keep the existing buffered USB variants as
baselines, and measure whether the new schedule fits its cycle budget before
implementing tokens, endpoint-zero enumeration and control OUT/IN transfers.

Production adoption also needs storage implementation, host-capability/version
changes, synthesis/mapped regression and full Tiny Tapeout physical checks.
The nine-protocol exploration and complete CAN/USB acceptance gates remain open.
