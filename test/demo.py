"""Exhaust meaningful inputs and vary every unused board control independently."""

import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def exhaustive_wrapper(dut):
    for a in range(16):
        for b in range(16):
            for choose in range(2):
                shared = a ^ b
                result = (shared & a) if choose else (shared | b)
                dut.ui_in.value = (b << 4) | a
                # Baseline plus each irrelevant bit individually toggled and all high.
                for unused in [0] + [1 << bit for bit in range(10)] + [1023]:
                    dut.uio_in.value = ((unused & 127) << 1) | choose
                    dut.clk.value = (unused >> 7) & 1
                    dut.rst_n.value = (unused >> 8) & 1
                    dut.ena.value = (unused >> 9) & 1
                    await Timer(1, unit="ns")
                    assert int(dut.uo_out.value) == (shared << 4) | result
                    assert int(dut.uio_out.value) == 0
                    assert int(dut.uio_oe.value) == 0
