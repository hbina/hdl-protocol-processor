"""Mode-0 peripheral peer for the compact firmware exploration image."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time

from test import PinController, firmware, load_program, reset
from tools.runtime import Request


async def peripheral(dut, expected, response):
    previous = int(dut.uio_out.value)
    assert previous & 1
    samples = []
    last_rise = None
    active = False
    while True:
        await ValueChange(dut.uio_out)
        now = int(dut.uio_out.value)
        assert int(dut.uio_oe.value) == 7
        if active and previous & 2 and now & 2:
            assert (previous ^ now) & 4 == 0, "MOSI changed during SCLK high"
        if previous & 1 and not now & 1:
            assert not active and not now & 2
            active = True
            await Timer(1, unit="ps")
            dut.uio_in.value = ((response[0] >> 7) & 1) << 3
        elif active and not previous & 2 and now & 2:
            samples.append((now >> 2) & 1)
            time = get_sim_time(unit="ns")
            if last_rise is not None and len(samples) % 8 != 1:
                assert time - last_rise == 10_000, "intrabyte SCLK must be 100 kHz"
            last_rise = time
        elif active and previous & 2 and not now & 2:
            assert get_sim_time(unit="ns") - last_rise == 4_960
            index = len(samples)
            if index < len(response) * 8:
                await Timer(1, unit="ps")
                dut.uio_in.value = ((response[index // 8] >> (7 - index % 8)) & 1) << 3
        if active and not previous & 1 and now & 1:
            assert not now & 2
            assert len(samples) == len(expected) * 8
            actual = bytes(
                sum(samples[i + j] << (7 - j) for j in range(8))
                for i in range(0, len(samples), 8)
            )
            assert actual == expected
            return
        previous = now


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_spi_probe_arbitrary_transactions(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    await load_program(dut, firmware("spi_probe.asm"))
    await Timer(100, unit="ns")
    controller = PinController(dut, 0x535049)
    rng = random.Random(0x535049)
    for ident, length in enumerate([1, 2, 63, 64, 1, 8, 64, 2]):
        tx = bytes(rng.randrange(256) for _ in range(length))
        rx = bytes(rng.randrange(256) for _ in range(length))
        peer = cocotb.start_soon(peripheral(dut, tx, rx))
        request = Request(ident, 1, input_count=length, output_limit=length)
        await controller.submit(request, tx)
        output, completion = await controller.complete(request, poll_limit=100_000)
        await with_timeout(peer, 20, "ms")
        assert output == [(byte, 0) for byte in rx]
        assert completion.status == 0 and completion.detail == 0
        assert await controller.read(0x101) == 0
        assert int(dut.uio_out.value) == 1
        assert int(dut.uio_oe.value) == 7
