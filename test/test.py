# SPDX-FileCopyrightText: © 2026 Protocol Emulator contributors
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge, Timer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.assembler import PROGRAM_WORDS, assemble  # noqa: E402


def firmware(name: str) -> list[int]:
    words = assemble((ROOT / "firmware" / name).read_text())
    assert len(words) <= PROGRAM_WORDS
    return words


async def reset(dut, pin_input: int = 0) -> None:
    await Timer(1, unit="ps")
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = pin_input
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def load_program(dut, words: list[int]) -> None:
    """Load words through ui[7:0], using three six-bit chunks per word."""

    dut.ui_in.value = 0x80
    await RisingEdge(dut.clk)

    for word in words:
        for shift in (0, 6, 12):
            chunk = (word >> shift) & 0x3F
            dut.ui_in.value = 0x80 | chunk
            await RisingEdge(dut.clk)
            dut.ui_in.value = 0xC0 | chunk
            await RisingEdge(dut.clk)
            dut.ui_in.value = 0x80 | chunk
            await RisingEdge(dut.clk)

    dut.ui_in.value = 0
    await RisingEdge(dut.clk)


async def sample_pins(dut, cycles: int) -> list[tuple[int, int]]:
    samples: list[tuple[int, int]] = []
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        samples.append((int(dut.uio_out.value), int(dut.uio_oe.value)))
    return samples


@cocotb.test()
async def test_protocol_firmware(dut):
    """Load and execute UART, SPI, and I2C firmware on the same core."""

    clock = Clock(dut.clk, 20, unit="ns")
    cocotb.start_soon(clock.start())

    # UART: decode the generated 8N1 waveform and verify 50 clocks per bit.
    await reset(dut)
    await load_program(dut, firmware("uart_tx.asm"))
    uart_samples = await sample_pins(dut, 560)

    start = next(
        index
        for index in range(1, len(uart_samples))
        if uart_samples[index - 1][0] & 1 and not uart_samples[index][0] & 1
    )
    assert all(oe & 0x01 for _, oe in uart_samples[start:])
    frame = [0] + [(0xA5 >> bit) & 1 for bit in range(8)] + [1]
    decoded = [uart_samples[start + 25 + 50 * bit][0] & 1 for bit in range(10)]
    assert decoded == frame

    # SPI mode 0: a permanently high MISO must produce 0xff in receive r1.
    await reset(dut, pin_input=0x08)
    await load_program(dut, firmware("spi_mode0.asm"))
    spi_samples = await sample_pins(dut, 260)

    rising_mosi: list[int] = []
    previous_clock = 0
    outputs_enabled = False
    for pin_out, pin_oe in spi_samples:
        clock_value = (pin_out >> 1) & 1
        outputs_enabled |= pin_oe & 0x06 == 0x06
        if outputs_enabled:
            assert pin_oe & 0x06 == 0x06
        if not previous_clock and clock_value:
            rising_mosi.append((pin_out >> 2) & 1)
        previous_clock = clock_value

    assert rising_mosi == [1, 0, 1, 0, 0, 1, 0, 1]
    await Timer(1, unit="ps")
    dut.ui_in.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.uo_out.value) == 0xFF

    # Pull-ups make SCL/SDA high when released. Holding SDA high models NACK.
    await reset(dut, pin_input=0x30)
    await load_program(dut, firmware("i2c_write.asm"))
    i2c_samples = await sample_pins(dut, 360)
    oe_values = [oe for _, oe in i2c_samples]

    start_drive = oe_values.index(0x20)
    clock_drive = oe_values.index(0x30, start_drive)
    assert start_drive < clock_drive
    assert oe_values[-1] == 0x10

    await Timer(1, unit="ps")
    dut.ui_in.value = 3
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.uo_out.value) & 1 == 1
