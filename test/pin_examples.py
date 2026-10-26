"""Pin-only tests shared by RTL and the freshly built mapped netlist."""

from pathlib import Path
import cocotb
from cocotb.triggers import Timer
from tools.assembler import assemble

ROOT = Path(__file__).resolve().parents[1]


async def tick(dut, count=1):
    for _ in range(count):
        dut.clk.value = 0
        await Timer(10, unit="ns")
        dut.clk.value = 1
        await Timer(10, unit="ns")


async def load(dut, name=None, source=None):
    dut.ena.value = 1
    dut.rst_n.value = 0
    dut.ui_in.value = 128
    dut.uio_in.value = 0
    await tick(dut, 3)
    dut.rst_n.value = 1
    await tick(dut, 3)
    words = assemble(
        source if source is not None else (ROOT / "firmware" / name).read_text()
    )
    for word in words:
        for shift in (0, 6, 12):
            value = 128 | ((word >> shift) & 63)
            dut.ui_in.value = value
            await tick(dut)
            dut.ui_in.value = value | 64
            await tick(dut)
            dut.ui_in.value = value
            await tick(dut)
    dut.ui_in.value = 0


@cocotb.test()
async def continuous_pin_copy(dut):
    await load(dut, "pin_copy.asm")
    for value in (0, 1, 0, 1, 1, 0):
        dut.ui_in.value = value
        await tick(dut, 9)
        assert int(dut.uo_out.value) & 1 == value
        assert int(dut.uio_oe.value) == 0
    # Dedicated input 14 is also the configuration write strobe, but in
    # execution toggling it must neither reload nor stop the program.
    dut.ui_in.value = 65
    await tick(dut, 9)
    assert int(dut.uo_out.value) & 1 == 1
    # Reload clears drivers and restarts independently of prior execution.
    await load(dut, "pin_copy.asm")
    dut.ui_in.value = 0
    await tick(dut, 9)
    assert int(dut.uo_out.value) == 0


@cocotb.test()
async def capture_and_replay(dut):
    await load(dut, "capture_replay.asm")
    pattern = [1, 0, 1, 1, 0, 0, 1, 0]
    observed = []
    for cycle in range(1, 120):
        dut.ui_in.value = pattern[min((cycle - 1) // 7, 7)]
        await tick(dut)
        if cycle in range(63, 113, 7):
            observed.append(int(dut.uo_out.value) & 1)
    assert observed == pattern, observed
    assert int(dut.uio_oe.value) == 0


@cocotb.test()
async def uart_tx(dut):
    await load(dut, "uart_tx.asm")
    # Wait for enabled idle high, then detect start falling edge.
    for _ in range(50):
        await tick(dut)
        if int(dut.uio_oe.value) & 1 and int(dut.uio_out.value) & 1:
            break
    else:
        raise AssertionError("no UART idle")
    for _ in range(50):
        await tick(dut)
        if not int(dut.uio_out.value) & 1:
            break
    else:
        raise AssertionError("no UART start")
    await tick(dut, 25)
    assert int(dut.uio_out.value) & 1 == 0
    value = 0
    for bit in range(8):
        await tick(dut, 50)
        value |= (int(dut.uio_out.value) & 1) << bit
    await tick(dut, 50)
    assert value == 0xA5 and int(dut.uio_out.value) & 1 == 1
    await tick(dut, 100)
    assert int(dut.uio_out.value) & 1 == 1


@cocotb.test()
async def spi_mode0(dut):
    await load(dut, "spi_mode0.asm")
    response = 0x3C
    sent = []
    previous = 0
    index = 0
    dut.uio_in.value = ((response >> 7) & 1) << 3
    for _ in range(400):
        await tick(dut)
        outputs = int(dut.uio_out.value)
        clock = (outputs >> 1) & 1
        if clock and not previous:
            sent.append((outputs >> 2) & 1)
        if previous and not clock:
            index += 1
            dut.uio_in.value = (
                ((response >> (7 - index)) & 1) if index < 8 else 0
            ) << 3
        previous = clock
    assert sent == [(0xA5 >> i) & 1 for i in range(7, -1, -1)], sent
    assert int(dut.uo_out.value) == response
    assert int(dut.uio_oe.value) == 6


@cocotb.test()
async def i2c_write(dut):
    # An independent open-drain peer supplies pullups, optional stretching,
    # and ACK/NACK. It sees resolved pins rather than processor internals.
    for nack in (False, True):
        await load(dut, "i2c_write.asm")
        previous_scl = 1
        started = False
        clocks = 0
        received = []
        stretched = False
        stretch_remaining = 0
        previous_oe = 0
        ack_active = False
        for _ in range(500):
            oe = int(dut.uio_oe.value)
            out = int(dut.uio_out.value)
            assert out & 0x30 == 0, "open drain must only drive zero"
            if started and previous_oe & 16 and not oe & 16 and not stretched:
                stretch_remaining = 5
                stretched = True
            scl = 0 if oe & 16 else 1
            if stretch_remaining:
                scl = 0
                stretch_remaining -= 1
            if previous_scl and not scl:
                if clocks == 8:
                    ack_active = True
                if clocks == 9:
                    ack_active = False
            sda = 0 if oe & 32 or (ack_active and not nack) else 1
            dut.uio_in.value = (scl << 4) | (sda << 5)
            if not started and scl == 1 and sda == 0:
                started = True
            if started and not previous_scl and scl:
                clocks += 1
                if clocks <= 8:
                    received.append(sda)
            previous_scl = scl
            previous_oe = oe
            await tick(dut)
        assert received == [(0xA0 >> i) & 1 for i in range(7, -1, -1)], received
        assert clocks == 9 and stretched
        assert int(dut.uo_out.value) == int(nack)


@cocotb.test()
async def all_wrapper_pins(dut):
    """Both banks, ui[6] reuse, pause, and reset via physical wrapper ports."""
    await load(
        dut,
        source="""
        LDI r2,255
        OE r2,0
    loop:
        IN r0,0
        OUT r0,0
        IN r1,1
        OUT r1,1
        JMP loop
    """,
    )
    for low, high in [(0xA5, 0x53), (0x3C, 0x2C), (255, 127), (0, 0)]:
        dut.uio_in.value = low
        dut.ui_in.value = high
        await tick(dut, 15)
        assert int(dut.uio_out.value) == low
        assert int(dut.uo_out.value) == high
        assert int(dut.uio_oe.value) == 255
    dut.ena.value = 0
    dut.uio_in.value = 255
    dut.ui_in.value = 127
    await tick(dut, 10)
    assert int(dut.uio_out.value) == 0 and int(dut.uo_out.value) == 0
    dut.ena.value = 1
    await tick(dut, 15)
    assert int(dut.uio_out.value) == 255 and int(dut.uo_out.value) == 127
    dut.rst_n.value = 0
    dut.ui_in.value = 128
    await tick(dut, 2)
    assert int(dut.uio_oe.value) == 0 and int(dut.uio_out.value) == 0
