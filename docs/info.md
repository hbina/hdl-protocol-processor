# Programmable Protocol Emulator

## How it works

This project implements a small programmable processor optimized for
cycle-accurate GPIO operations. Firmware programs will read and write pins,
wait for precise intervals, shift data, and branch on sampled inputs. The
initial protocol targets are UART, SPI, and I2C.

The first version has 64 16-bit program words, four 8-bit registers, an 8-bit
delay counter, and eight independently controlled bidirectional pins. Programs
are uploaded after reset through the dedicated input pins. See
[the design report](design.md) for the ISA and external interface.

## How to test

Install uv and an RTL simulator, then run:

```sh
uv sync --locked
uv run make -C test
```

Use `SIM=verilator` to select Verilator instead of the default Icarus Verilog
simulator. Automated tests upload and execute the UART, SPI, and I2C firmware
and verify the resulting waveforms and sampled data.

## External hardware

No external hardware is required for software simulation. An FPGA development
board and Pmod breakouts may later be used for interoperability testing with
real UART, SPI, and I2C devices.
