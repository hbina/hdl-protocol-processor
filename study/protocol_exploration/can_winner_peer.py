"""Independent competing CAN transmitter; DUT must receive/ACK the winner."""

import json
import os
import random
from pathlib import Path

import cocotb
from can_peer import frame
from can_recovery_peer import BIT, RecoveryPeer, retry_request, until
from can_tx_peer import Receiver
from cocotb.clock import Clock
from cocotb.triggers import SimTimeoutError, Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time
from frontier_peer import rx, tx
from generic_frontier import assemble

from test import PinController, load_program, reset
from tools.runtime import Request


class ArbitrationPeer(RecoveryPeer):
    async def sof(self):
        while self.drive() != 0:
            await ValueChange(self.dut.uio_out)
            await Timer(1, unit="ps")
        return int(get_sim_time(unit="ps"))

    async def compete(
        self,
        identifier,
        payload,
        winners,
        *,
        final_transmit=True,
        corrupt=False,
        ack_failures=0,
    ):
        records = []
        ours, _, _ = frame(identifier, payload)
        previous_end = None
        for winner_id, winner_data in winners:
            wire, ack, _ = frame(winner_id, winner_data, crc_error=corrupt)
            loss = next(index for index, (a, b) in enumerate(zip(ours, wire)) if a != b)
            assert ours[loss] == 1 and wire[loss] == 0 and winner_id < identifier
            start = await with_timeout(self.sof(), 2, "ms")
            if previous_end is not None:
                assert start >= previous_end - 1000
            for index, bit in enumerate(wire):
                # The competing transmitter releases ACK. There is no third
                # receiver: only a real DUT ACK can acknowledge this winner.
                self.sender = bit
                await until(start + index * BIT + BIT * 3 // 4)
                expected = (
                    ours[index] if index <= loss else int(index != ack or corrupt)
                )
                assert self.drive() == expected, (
                    winner_id,
                    index,
                    loss,
                    self.drive(),
                    expected,
                )
                resolved = self.sender & self.drive()
                assert resolved == (0 if index == ack and not corrupt else bit)
                await until(start + (index + 1) * BIT)
            self.sender = 1
            previous_end = start + len(wire) * BIT
            records.append(
                {
                    "winner_id": winner_id,
                    "winner_dlc": len(winner_data),
                    "sof_ps": start,
                    "loss_wire_bit": loss,
                    "intermission_end_ps": previous_end,
                    "crc_corrupt": corrupt,
                }
            )
        if final_transmit:
            if ack_failures:
                retries = await self.retries(
                    identifier, payload, [False] * ack_failures + [True]
                )
                assert (
                    previous_end is None or retries[0]["sof_ps"] >= previous_end - 1000
                )
                records.extend(retries)
            else:
                start_ns, bit_ns, count = await with_timeout(
                    Receiver.listen(self, identifier, payload), 2, "ms"
                )
                final_start = round(start_ns * 1000)
                assert previous_end is None or final_start >= previous_end - 1000
                records.append(
                    {
                        "retried_sof_ps": final_start,
                        "completion_earliest_ps": final_start + bit_ns * count * 1000,
                        "idle_after_winner_ps": final_start - previous_end
                        if previous_end
                        else None,
                    }
                )
        try:
            await with_timeout(ValueChange(self.dut.uio_out), 400, "us")
        except SimTimeoutError:
            return records
        raise AssertionError(
            "Unexpected transmission after completed/exhausted request"
        )


async def setup(dut):
    assert os.environ.get("CAN_WINNER_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = ArbitrationPeer(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(
        dut, assemble(Path(__file__).with_name("can_winner_candidate.asm").read_text())
    )
    return PinController(dut, 0x57494E), bus


async def winner_request(
    controller,
    bus,
    ident,
    identifier,
    payload,
    winners,
    *,
    status=0,
    final_transmit=True,
    corrupt=False,
    ack_failures=0,
):
    listener = cocotb.start_soon(
        bus.compete(
            identifier,
            payload,
            winners,
            final_transmit=final_transmit,
            corrupt=corrupt,
            ack_failures=ack_failures,
        )
    )
    request = Request(
        ident, 4, arguments_length=3, input_count=len(payload), output_limit=33
    )
    await controller.submit(
        request, payload, bytes([identifier >> 8, identifier & 255, len(payload)])
    )
    output, event = await controller.complete(request, poll_limit=100000)
    completed_at = int(get_sim_time(unit="ps"))
    records = await listener
    expected = (
        []
        if corrupt
        else [
            (byte, 0)
            for winner_id, data in winners
            for byte in bytes([winner_id >> 8, winner_id & 255, len(data)]) + data
        ]
    )
    assert output == expected, (output, expected)
    assert event.status == status and event.detail == len(winners) + ack_failures + int(
        final_transmit
    ), event
    assert event.input_consumed == len(payload) and event.output_produced == len(
        expected
    ), event
    assert await controller.read(0x101) == 0 and bus.drive() == 1
    if final_transmit:
        assert completed_at >= records[-1]["completion_earliest_ps"] - 1000
    elif not corrupt:
        assert completed_at >= records[-1]["intermission_end_ps"] - 1000
    return records


@cocotb.test(timeout_time=60, timeout_unit="ms")
async def test_winner_reception_and_retained_payload(dut):
    controller, bus = await setup(dut)
    rng = random.Random(0x415242)
    records = []
    for bit in range(11):
        length = bit % 9
        payload = bytes(rng.randrange(256) for _ in range(length))
        winner_data = bytes(rng.randrange(256) for _ in range(8 - length))
        records += await winner_request(
            controller, bus, bit, 1 << bit, payload, [(0, winner_data)]
        )
    records += await winner_request(
        controller, bus, 12, 0x7FF, b"\xff" * 8, [(0x7FE, bytes(8))]
    )
    Path("winner_timings.json").write_text(json.dumps(records, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_repeated_winners_exhaustion_and_bad_crc(dut):
    controller, bus = await setup(dut)
    await winner_request(
        controller,
        bus,
        20,
        0x7FF,
        b"\x01\x23\x45\x67\x89\xab\xcd\xef",
        [(0x123, b"\xa5"), (0x456, b"\x5a" * 8)],
    )
    await winner_request(
        controller,
        bus,
        21,
        0x7FF,
        b"\xff" * 8,
        [(0x123, b"\x55" * 8), (0x456, b"\xaa" * 8), (0x7FE, b"\x5a" * 8)],
        status=22,
        final_transmit=False,
    )
    await rx(controller, bus, 22, 0x321, b"\x12")
    await winner_request(
        controller,
        bus,
        23,
        0x7FF,
        b"\xff",
        [(0x123, b"\xa5")],
        status=16,
        final_transmit=False,
        corrupt=True,
    )
    await winner_request(controller, bus, 24, 0x456, b"\x55\xaa", [(0x123, b"\x5a")])


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def test_winner_image_legacy_and_ack_recovery(dut):
    controller, bus = await setup(dut)
    await tx(controller, bus, 30, 0x123, b"\xa5")
    await rx(controller, bus, 31, 0x456, b"\x5a")
    await tx(controller, bus, 32, 0x7FF, b"\x55", winner=0x3FF, status=22)
    await retry_request(controller, bus, 33, 0x321, b"\xff" * 8, [False, False, True])
    await retry_request(controller, bus, 34, 0x321, b"\xa5", [False] * 3, status=24)
    await retry_request(
        controller, bus, 35, 0x321, b"\xa5", [False], status=25, stuck=True, echo_bits=0
    )
    await winner_request(controller, bus, 36, 0x7FF, b"\xaa" * 8, [(0x123, bytes(8))])
    await winner_request(
        controller,
        bus,
        37,
        0x7FF,
        b"\x55\xaa\xff\x00",
        [(0x123, b"\x12\x34")],
        ack_failures=1,
    )
