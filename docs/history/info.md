> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Programmable Pin Processor

## How it works

An autonomous processor reads synchronized input pins, executes uploaded
firmware with private RAM, and drives output values/enables. The core has
256×16-bit instructions, four 8-bit registers, 256 bytes of RAM, and configurable
1..256 input/output counts. The Tiny Tapeout wrapper exposes 15 inputs and
16 outputs, including eight bidirectional uio pads. ui[7] selects configuration;
there is no execution-time host request/response layer.

See [the current architecture](pin_processor.md), [examples](../firmware/README.md),
and [current status](../README.md). Earlier runtime studies are historical.

## How to test

```sh
uv sync --locked
uv run --locked pytest
uv run --locked make -B -C test
```

Use SIM=verilator for the second simulator. Tests load complete example programs
and check GPIO waveforms and pin-visible received data. Physical implementation
and mapped tests must be regenerated for this architecture.

## External hardware

Simulation needs no external hardware. I2C uses external pullups on real boards.
FPGA/board interoperability, CDC/MTBF signoff, and full protocol stacks remain open.
