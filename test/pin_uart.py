"""8N1 firmware integration against independent UART peers, using real RTL."""

from __future__ import annotations
import cocotb
from cocotb.triggers import Timer
from cocotb.utils import get_sim_time
from firmware.uart import transmit, receive, echo
from uart_peer import (
    boot,
    send,
    read_tx,
    status,
    wait_status,
    tx_edges,
    expected_edges,
    ram,
)


@cocotb.test()
async def ram_transmit_all_bytes(dut):
    for block in range(4):
        payload = bytes(range(block * 64, (block + 1) * 64))
        clock = await boot(dut, transmit.generate(payload=payload).words)
        edges = []
        monitor = cocotb.start_soon(tx_edges(dut, edges))
        # Two complete buffer passes prove pointer wrap and repeat without reload.
        got = []
        starts = []
        for _ in range(128):
            value, start = await read_tx(dut)
            got.append(value)
            starts.append(start)
        assert bytes(got) == payload * 2
        assert all(b - a == 10_000_000 for a, b in zip(starts, starts[1:])), starts[:5]
        edge_start = next(t for t, v in edges if v == 0)
        assert 0 <= starts[0] - edge_start <= 20_000
        reference = expected_edges(payload * 2, edge_start, 1000)
        actual = [(t, v) for t, v in edges if edge_start <= t <= reference[-1][0]]
        assert actual == reference, (actual[:12], reference[:12])
        memory = ram(dut)
        if memory is not None:
            assert bytes(int(memory[i].value) for i in range(64)) == payload
        monitor.cancel()
        clock.cancel()


@cocotb.test()
async def continuous_receive_and_overflow(dut):
    clock = await boot(dut, receive.generate(capacity=16).words)
    await wait_status(dut, 2)
    await Timer(1000, unit="ns")
    payload = bytes([0, 255, 0x55, 0xAA, *range(12)])
    for index, value in enumerate(payload):
        await send(dut, value)
        assert int(dut.uo_out.value) == value, (index, value)
    assert status(dut, 7) == 1 and status(dut, 6) == 0
    memory = ram(dut)
    if memory is not None:
        assert bytes(int(memory[i].value) for i in range(16)) == payload
    # Drop-new preserves the original payload and last accepted output.
    for value in range(19):
        await send(dut, value)
    await Timer(1000, unit="ns")
    assert status(dut, 6) == 1 and status(dut, 3) == 0
    assert int(dut.uo_out.value) == payload[-1]
    if memory is not None:
        assert bytes(int(memory[i].value) for i in range(16)) == payload
        assert int(memory[243].value) == 19
        assert int(memory[241].value) == int(memory[242].value) == 0
    clock.cancel()


@cocotb.test()
async def echo_every_byte(dut):
    clock = await boot(dut, echo.generate().words)
    memory = ram(dut)
    for value in range(256):
        await wait_status(dut, 2)
        # Sender waits for READY plus a full idle bit; only one byte in flight.
        await Timer(1000, unit="ns")
        reply = cocotb.start_soon(read_tx(dut))
        await send(dut, value, phase_ns=(value % 20) + 0.125)
        got, _ = await reply
        assert got == value, (value, got)
        assert int(dut.uo_out.value) == value
        if memory is not None:
            assert int(memory[0].value) == value
        assert status(dut, 4) == status(dut, 5) == 0
        await wait_status(dut, 2)
    clock.cancel()


@cocotb.test()
async def receive_phase_and_baud_mismatch(dut):
    for baud in [1_000_000, 250_000, 115_200, 9_600]:
        period = (50_000_000 + baud // 2) // baud
        bit_ns = period * 20
        for ratio in [0.98, 1.0, 1.02]:
            clock = await boot(dut, receive.generate(baud=baud, capacity=64).words)
            await wait_status(dut, 2, timeout_ns=bit_ns * 5)
            await Timer(bit_ns, unit="ns")
            payload = bytes([0, 255, 0x55, 0xAA, 1, 128, 0x7F, 0xFE] * 4)
            # Different phase offsets, then uninterrupted back-to-back frames.
            await Timer(7.375, unit="ns")
            for value in payload:
                await send(dut, value, bit_ns=bit_ns * ratio)
            await Timer(bit_ns, unit="ns")
            memory = ram(dut)
            if memory is not None:
                assert bytes(int(memory[i].value) for i in range(32)) == payload, (
                    baud,
                    ratio,
                )
            assert int(dut.uo_out.value) == payload[-1]
            assert status(dut, 4) == status(dut, 5) == status(dut, 6) == 0, (
                baud,
                ratio,
            )
            clock.cancel()


@cocotb.test()
async def errors_break_and_recovery(dut):
    for module in [receive, echo]:
        clock = await boot(dut, module.generate().words)
        await wait_status(dut, 2)
        await Timer(1000, unit="ns")
        # A short low pulse must fail the mid-start check, not publish a byte.
        for width in [40, 120, 200]:
            dut.uio_in.value = 0
            await Timer(width, unit="ns")
            dut.uio_in.value = 2
            await Timer(4000, unit="ns")
        assert status(dut, 4) == 1 and status(dut, 3) == 0
        memory = ram(dut)
        if memory is not None:
            assert int(memory[241].value) == 3
        await wait_status(dut, 2)
        await send(dut, 0x33, stop=0)
        await Timer(4000, unit="ns")
        assert status(dut, 5) == 1 and status(dut, 3) == 0
        if memory is not None:
            assert int(memory[242].value) == 1
        await wait_status(dut, 2)
        # A sustained break is reported once, then requires a fresh idle interval.
        dut.uio_in.value = 0
        await Timer(100_000, unit="ns")
        assert status(dut, 2) == 0 and status(dut, 3) == 0
        if memory is not None:
            assert int(memory[242].value) == 2
        dut.uio_in.value = 2
        await wait_status(dut, 2)
        await Timer(1000, unit="ns")
        reply = cocotb.start_soon(read_tx(dut)) if module is echo else None
        await send(dut, 0xA6)
        if reply is not None:
            value, _ = await reply
            assert value == 0xA6
        assert int(dut.uo_out.value) == 0xA6 and status(dut, 3) == 1
        assert status(dut, 4) == status(dut, 5) == 1, "error flags are sticky"
        if memory is not None:
            assert int(memory[0].value) == 0xA6
        clock.cancel()


@cocotb.test()
async def echo_baud_and_busy_contract(dut):
    for clock_hz, baud in [
        (50_000_000, 1_000_000),
        (50_000_000, 115_200),
        (50_000_000, 9_600),
        (25_000_000, 500_000),
    ]:
        period = (clock_hz + baud // 2) // baud
        bit_ns = period * 1_000_000_000 / clock_hz
        clock = await boot(
            dut, echo.generate(clock_hz=clock_hz, baud=baud).words, clock_hz=clock_hz
        )
        await wait_status(dut, 2, timeout_ns=bit_ns * 5)
        for value in [0, 255, 0x55, 0xA5]:
            await Timer(bit_ns, unit="ns")
            reply = cocotb.start_soon(read_tx(dut, bit_ns=bit_ns))
            await send(dut, value, bit_ns=bit_ns)
            got, start = await reply
            assert got == value
            assert status(dut, 2) == 0, "READY must remain low through TX stop"
            await wait_status(dut, 2, timeout_ns=bit_ns * 5)
            assert get_sim_time(unit="ps") >= start + 10 * bit_ns * 1000
        clock.cancel()


@cocotb.test()
async def echo_busy_traffic_and_recovery(dut):
    clock = await boot(dut, echo.generate().words)
    await wait_status(dut, 2)
    await Timer(1000, unit="ns")
    reply = cocotb.start_soon(read_tx(dut))
    await send(dut, 0x5A)
    assert status(dut, 2) == 0
    # Deliberately violate READY. This all-zero frame overlaps TX and must
    # not overwrite the accepted byte. Other busy waveforms are unsupported;
    # the documented sender contract is to wait for READY, then an idle bit.
    await send(dut, 0)
    value, _ = await reply
    assert value == 0x5A
    await wait_status(dut, 2)
    assert int(dut.uo_out.value) == 0x5A
    memory = ram(dut)
    if memory is not None:
        assert int(memory[0].value) == 0x5A
    await Timer(2000, unit="ns")
    assert status(dut, 0) == 1
    reply = cocotb.start_soon(read_tx(dut))
    await send(dut, 0x96)
    value, _ = await reply
    assert value == 0x96
    clock.cancel()


@cocotb.test()
async def ram_transmit_other_bauds(dut):
    for baud in [115_200, 9_600]:
        period = (50_000_000 + baud // 2) // baud
        bit_ns = period * 20
        payload = bytes([0, 255, 0x55, 0xAA])
        clock = await boot(dut, transmit.generate(baud=baud, payload=payload).words)
        edges = []
        monitor = cocotb.start_soon(tx_edges(dut, edges))
        got = []
        for _ in range(8):
            value, _ = await read_tx(dut, bit_ns=bit_ns)
            got.append(value)
        assert bytes(got) == payload * 2
        start = next(t for t, v in edges if v == 0)
        reference = expected_edges(payload * 2, start, bit_ns)
        assert [(t, v) for t, v in edges if start <= t <= reference[-1][0]] == reference
        monitor.cancel()
        clock.cancel()


@cocotb.test()
async def receive_capacity_boundaries(dut):
    for capacity, drops in [(1, 261), (240, 2)]:
        clock = await boot(dut, receive.generate(capacity=capacity).words)
        await wait_status(dut, 2)
        await Timer(1000, unit="ns")
        payload = bytes(range(capacity))
        for value in payload:
            await send(dut, value)
        assert status(dut, 7) == 1 and status(dut, 3) == 1
        for _ in range(drops):
            await send(dut, 0xA5)
        await Timer(1000, unit="ns")
        assert status(dut, 6) == 1
        assert int(dut.uo_out.value) == payload[-1]
        memory = ram(dut)
        if memory is not None:
            assert bytes(int(memory[i].value) for i in range(capacity)) == payload
            assert int(memory[243].value) == drops % 256
            assert int(memory[241].value) == int(memory[242].value) == 0
        clock.cancel()
