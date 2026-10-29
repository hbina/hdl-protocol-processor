# A larger combinational example: IPv4 header checksum

[The construction script](../examples/combinational/ipv4_checksum.py) consumes an
entire 20-byte header at once on a 160-bit input. The first network byte occupies
`header[159:152]`; the checksum field at bytes 10–11 occupies `header[79:64]`.

It produces:

- `checksum[15:0]`: the checksum to insert, ignoring the existing checksum field.
- `valid`: whether the supplied header, including its checksum field, has a
  one's-complement sum of `0xffff`.

This implements the sum/complement algorithm described in
[RFC 1071](https://www.rfc-editor.org/rfc/rfc1071.html). The component is a checksum
primitive, not an IPv4 parser or protocol engine: it does not check version,
header length, packet boundaries, or payload. Options and streaming are excluded.
The input need not contain a semantically valid IPv4 header to be checksummed.

The `wide_sum` Python helper constructs a balanced adder tree. It extends the
nine non-checksum words to 20 bits, preserving every carry. The exact sum node is
shared between generation and validation. `fold_sum16` constructs explicit
end-around carries, then generation complements the folded sum. Validation adds
the provided checksum word to the shared sum and checks the folded result.
All helpers run in Python during construction. There are no HDL calls, registers,
clocks, runtime allocation, or automatic compiler optimizations.

```sh
uv run --locked python -m combhdl examples/combinational/ipv4_checksum.py \
  --component component --output build/ipv4_checksum
cat build/ipv4_checksum/ipv4_checksum.v
cat build/ipv4_checksum/ast.txt
uv run --locked python -m tools.check_checksum --sim icarus
uv run --locked python -m tools.check_checksum --sim verilator
uv run --locked python -m tools.check_synthesis --yosys .venv/bin/yowasp-yosys
```

With the existing local Verilator build, append
`--executable .asic-tools/verilator/bin/verilator` to `check_checksum`.

```python
from combhdl import evaluate
from examples.combinational.ipv4_checksum import component

header = int("450000730000400040110000c0a80001c0a800c7", 16)
assert evaluate(component, {"header": header}) == {"checksum": 0xB861, "valid": 0}
header |= 0xB861 << 64
assert evaluate(component, {"header": header}) == {"checksum": 0xB861, "valid": 1}
```

After generating the artifacts above, import the standalone model from the
repository root (no compiler dependency is needed to execute `model.py`):

```python
from build.ipv4_checksum.model import ipv4_checksum

header = int("450000730000400040110000c0a80001c0a800c7", 16)
assert ipv4_checksum(header=header) == {"checksum": 0xB861, "valid": 0}
header |= 0xB861 << 64
assert ipv4_checksum(header=header) == {"checksum": 0xB861, "valid": 1}
```

`model.py` preserves shared sums as single assignments and masks intermediate
arithmetic. Its keyword-only function rejects invalid unsigned inputs with
`ValueError`. Python evaluation gives functional values, without modeling hardware
timing or concurrency.

Verification uses an independent byte-oriented integer oracle that folds carry
after each word, rather than reproducing the expression tree. The 2,508 HDL
vectors include all-zero/all-one data, every single-bit position and complement,
known checksums (`0xb861` and the RFC numerical example `0x220d`), 512 seeded
random headers, corrected valid headers, and single-bit corruption of each valid
header. The generated Python model also agrees with the independent oracle and
graph evaluator on all 2,508 vectors (`test/compiler/test_python.py::test_checksum_vectors`).
Additional Python checks exercise end-around carry and helper validation.

Both Icarus 12.0 and Verilator 5.038 agree with the independent oracle and graph
evaluator for every vector. Generic Yosys 0.70 synthesis reports **1,019 cells**,
zero storage, and zero combinational loops. This is not mapped ASIC area or
physical timing. The example is too wide for the demo's board interface and is
not in the Tiny Tapeout source list. Commands, tool versions, source hashes, and
statistics are recorded in [checksum_results.json](checksum_results.json).
