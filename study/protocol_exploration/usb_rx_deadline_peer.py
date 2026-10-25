"""Intentionally failing deadline requirement for the buffered packet probe."""

import cocotb
from usb_rx_peer import receive, setup


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_usb_ack_turnaround_requirement(dut):
    controller, phy = await setup(dut)
    latency = await receive(controller, phy, 1, b"\xff" * 8, ack=True)
    # USB2 section7.1.18.1: detachable-device maximum6.5 LS bit times,
    # measured from EOP SE0->J to response J->K. Captive7.5 is also reported.
    maximum_ps = 6.5 * 1_000_000_000_000 / 1_500_000
    assert latency <= maximum_ps, (
        f"ACK latency {latency / 1_000_000:.3f} us exceeds detachable-device maximum {maximum_ps / 1_000_000:.3f} us"
    )
