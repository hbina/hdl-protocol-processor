"""Independent UART wire driver/decoder and configuration-pin loader."""

from __future__ import annotations
import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, ValueChange
from cocotb.utils import get_sim_time


async def tick(dut, count=1):
    for _ in range(count):
        dut.clk.value = 0
        await Timer(10, unit="ns")
        dut.clk.value = 1
        await Timer(10, unit="ns")


async def boot(dut, words, *, clock_hz=50_000_000):
    dut.ena.value = 1
    dut.rst_n.value = 0
    dut.ui_in.value = 128
    dut.uio_in.value = 2  # External RX is idle high throughout configuration.
    await tick(dut, 3)
    dut.rst_n.value = 1
    await tick(dut, 3)
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
    dut.clk.value = 0
    return cocotb.start_soon(
        Clock(dut.clk, 1_000_000_000 / clock_hz, unit="ns").start()
    )


def status(dut, bit):
    return (int(dut.uio_out.value) >> bit) & 1


async def wait_status(dut, bit, value=1, timeout_ns=100_000):
    deadline = get_sim_time(unit="ns") + timeout_ns
    while status(dut, bit) != value:
        assert get_sim_time(unit="ns") < deadline, f"pin {bit} never became {value}"
        await Timer(20, unit="ns")


async def send(dut, value, *, bit_ns=1000, phase_ns=0, stop=1):
    if phase_ns:
        await Timer(phase_ns, unit="ns")
    for level in [0, *[(value >> bit) & 1 for bit in range(8)], stop]:
        dut.uio_in.value = level << 1
        await Timer(bit_ns, unit="ns")
    dut.uio_in.value = 2


async def read_tx(dut, *, bit_ns=1000):
    # Return at the stop midpoint, leaving time to arm for a back-to-back frame.
    deadline = get_sim_time(unit="ns") + bit_ns * 50
    while not status(dut, 0):
        assert get_sim_time(unit="ns") < deadline, "TX did not become idle"
        await Timer(20, unit="ns")
    while status(dut, 0):
        assert get_sim_time(unit="ns") < deadline, "no TX start"
        await Timer(20, unit="ns")
    start = get_sim_time(unit="ps")
    await Timer(bit_ns / 2, unit="ns")
    assert status(dut, 0) == 0, "invalid TX start"
    value = 0
    for bit in range(8):
        await Timer(bit_ns, unit="ns")
        value |= status(dut, 0) << bit
    await Timer(bit_ns, unit="ns")
    assert status(dut, 0) == 1, "invalid TX stop"
    return value, start


async def tx_edges(dut, result):
    previous = status(dut, 0)
    while True:
        await ValueChange(dut.uio_out)
        level = status(dut, 0)
        if level != previous:
            result.append((get_sim_time(unit="ps"), level))
        previous = level


def expected_edges(payload, start, bit_ns):
    result = []
    previous = 1
    for frame, value in enumerate(payload):
        for bit, level in enumerate([0, *[(value >> i) & 1 for i in range(8)], 1]):
            if level != previous:
                result.append(
                    (start + round((frame * 10 + bit) * bit_ns * 1000), level)
                )
            previous = level
    return result


def ram(dut):
    # RTL must expose RAM: never silently skip the storage/counter assertions.
    # A mapped netlist has no guaranteed memory hierarchy; check pins there.
    if os.environ.get("GATES") == "yes":
        return None
    return dut.user_project.core.memory
