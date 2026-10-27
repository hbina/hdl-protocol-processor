# Standalone pin-driven examples

All examples target a 50 MHz clock and fit the 256-word processor. Build one:

```sh
uv run --locked python -m tools.assembler firmware/pin_copy.asm --disassemble
```

Upload the resulting 16-bit words using the configuration procedure in
[the architecture](../docs/pin_processor.md). Run all pin-level examples with
`uv run --locked make -B -C test`; select one with
`COCOTB_TEST_FILTER=uart_tx` (or the corresponding test name below).

| Program | Words | Pins and observable behavior | Test name |
|---|---:|---|---|
| pin_copy.asm | 3 | ui[0] continuously copied to uo[0]; no output enable needed | continuous_pin_copy |
| capture_replay.asm | 15 | Eight ui[0] samples stored in RAM[0..7], then replayed on uo[0], seven clocks per sample | capture_and_replay |
| uart_tx.asm | 18 | uio[0] sends 0xA5 as 8N1 at 1 Mbaud, then holds high | uart_tx |
| spi_mode0.asm | 24 | uio[1]=SCLK, uio[2]=MOSI, uio[3]=MISO; sends 0xA5, stores received byte in RAM[0] and publishes it on uo | spi_mode0 |
| i2c_write.asm | 36 | uio[4]=SCL, uio[5]=SDA; open-drain address 0xA0 write, ACK/NACK in RAM[0] and uo[0] | i2c_write |

Each file contains its own complete implementation. There are no generated
experiment chains, variant catalogs, or firmware-builder framework. These are
small examples, not complete configurable protocol stacks. I2C requires pullups,
allows clock stretching, and intentionally ends with SCL low after ACK sampling;
it does not implement a full transaction or STOP sequence. Input samples include
synchronizer latency. RAM must be initialized before reads.

`historical/` contains superseded request-based firmware and is excluded from
active snapshots and validation.

## Continuous UART programs

The fixed-byte UART file above remains a small introductory example. The independent
[UART programs](uart/README.md) add RAM-backed repeating TX, bounded continuous RX,
and sequential echo, with baud generation, error flags/counters, and explicit
traffic limits. Their default listings are also part of the active ISA snapshot.
