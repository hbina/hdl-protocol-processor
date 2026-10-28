> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Validated UART runtime and software-clock deadlines

2026-10-25. The original UART runtime ABI now passes six test groups on the
existing isolated1024×18/eight-register model. The **251-word image does not
fit the production128-word core**. No production RTL, instruction semantics,
clock counter or timer peripheral has changed.

The [builder](../study/protocol_exploration/build_uart_runtime.py) emits the
[candidate](../study/protocol_exploration/uart_runtime_candidate.asm).
The named [acceptance module](../test/test_uart_runtime.py) implements the plan's
request, wire and timing checks. The planned `firmware/uart_runtime.asm` remains
blocked by measured capacity: oversized candidates stay in `study/` so the
production firmware-fit check remains honest. The107-word production probe and
its source-bound evidence are unchanged.

## Implemented ABI

The request/response contract follows the
[original UART milestone](protocol_exploration.md#first-implementation-milestone-uart-txrx):
TX=1, RX=2, TX_THEN_RX=3; parameters at address0/length4 are
`[receive_count, timeout_windows, 0, 0]`. Counts are0–64 and windows1–255.
TX requires zero receive count/output limit, RX requires no input, and receive
operations require enough output capacity. Zero-length operations are no-ops.
Flags, reserved bytes, addresses/lengths and buffered-input occupancy are checked
before protocol activity. Invalid requests drain actual prebuffered input so
ownership can be released. Terminal input counts include discarded bytes.

Statuses are0 OK,1 BAD_RECORD,2 BAD_OPERATION,3 BAD_ARGUMENTS,4 BAD_LENGTH,
6 RX_TIMEOUT and7 FRAMING_ERROR. High bytes of request address/length/count
fields produce BAD_RECORD. Invalid-stop bytes are discarded while earlier
valid bytes remain in the result with metadata0. IDs, counts and zero detail/
reserved fields are checked. The runtime transport error namespace is unchanged.

TX=uio0, RX=uio1, output enable0x01; all other protocol pins are inputs.
TX is idle high. Diagnostic r3 is0 outside RX and0xa5 while armed. The peer
waits two bit periods after observing arming before supplying bytes. Input
must be observed high before the first start; a framing failure cannot turn
an indefinitely low line into a new frame on the next request. Each valid
stop qualifies idle for a back-to-back next frame. Hardware needs the same
logic-level UART/voltage boundary as the original probe; no UART controller
is external or hardwired inside the ASIC.

## Deadline implementation and cycle evidence

Register r4:r5:r6 stores remaining search clocks as a24-bit integer. Initialization
loads `timeout_windows * 65536`. A normal pin-search path consumes and subtracts
exactly32 clocks. A low candidate is checked around the middle of its start bit;
if rejected, that path consumes and subtracts exactly256 clocks, including its
qualification delay. Branch and borrow paths are balanced with generic WAIT/NOP.
False starts therefore consume the same deadline instead of replenishing it.

Quiet expiry measures exactly65,536,131,072 and196,608 clocks for windows1/2/3.
The false-start storm also measures65,536 clocks in its tested phase. An expiry
inside a rejected candidate path may overshoot by at most224 clocks; this is a
derived bound from the32/256-clock debits, not a measured maximum over all phases.
Event publication and asynchronous host polling add separate bounded firmware/
transport latency after search expiry. Start-search detection jitter is at most
one32-clock polling period plus input synchronization. A qualified frame has a
fixed finite sampling path; it does not keep extending the start-search deadline.

The deadline restarts after each valid byte. TX/data sampling periods are434
core clocks at50 MHz. No-RX-first-response, between-byte timeout, low stop,
initially/persistently low line and short false starts have recovery tests.
Windows255 is exercised with successful data; its full quiet timeout is not
simulated. The334.234 ms maximum window is derived from the counter width/
initialization. Unit tests independently execute the emitted debit instructions
against integer subtraction for fixed boundaries and500 seeded24-bit values.
They verify exact clock cost, expiration/borrow behavior, and preservation of
idle/arming registers.

All eight registers are used. Scratch consists of the16-byte request,16-byte
event and one remaining-RX-count byte:33 bytes at128–160. The UART protocol
still runs entirely through ordinary generic pin, branch, shift and memory
operations. This is an additional concrete use of the generic register expansion;
it provides no evidence that a dedicated protocol timer is required.

## Tests and reproduction

```sh
uv run --locked pytest -q test/test_uart_runtime_units.py
# Expected exit1:251 words exceeds128. This is a measured candidate size,
# not a lower bound on every possible UART implementation.
uv run --locked python study/protocol_exploration/run_uart_runtime.py
# Isolated generic model, not supported production/mapped firmware.
uv run --locked python study/protocol_exploration/run_uart_runtime.py --expanded-model
```

The [evidence snapshot](uart_runtime_results.json) records exact commands,
source/XML hashes, capacity diagnostic and timing traces. Six groups cover:

- TX, RX and sequential TX_THEN_RX at lengths0/1/2/63/64; varied bytes, IDs,
  repeated requests without reset/reload, boundary patterns and windows255.
- Exact quiet-clock expiry for windows1/2/3, followed by a successful receive.
- Five input phases across a20 ns core period and sender rates−1%/0/+1%, with
  back-to-back frames; false start, invalid stop and partial-result timeout.
- False-start storms, framing failure followed by low-line timeout, then recovery.
-28 malformed requests with input draining, exact status/count checks and no TX
  activity, followed by a successful exchange.
- Reset during TX and partial RX: output enables release during reset, followed
  by reload and a successful exchange. Ordinary repeated-request tests do not reset.

The independent sender/decoder from the frozen probe checks actual TX pins and
supplies distinct RX bytes. Runtime completion polling concurrently exercises
asynchronous host reads. PC traces measure deadline clocks only; expected UART
bytes never come from internal DUT state. Two new units check source generation/
capacity and the emitted software-clock accounting.

## Remaining production/verification work

- Resolve code density or generic storage/register capacity. The candidate is
  not installed as production firmware, and there is no251-word production netlist.
- Revalidate instruction timing if future memory changes add fetch latency;
  software-clock accounting and UART434-clock paths rely on current semantics.
- Expanded-model mapped/Verilator verification and board interoperability are
  unverified. Historical physical results remain tied to their unchanged sources.
- Review/commit the project changes in recoverable increments; the current
  worktree is not itself a set of committed baselines.

The next functional task is JTAG invalid-request/length handling, followed by
CAN winner reception, retry/resynchronization and error-frame attempts. The
nine-protocol acceptance goal remains open.
