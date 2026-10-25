"""Independent resolved open-drain I2C register target for the capacity study."""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Event, First, Timer, ValueChange
from cocotb.utils import get_sim_time

from test import PinController, load_program, reset
from tools.runtime import Request
from run_i2c import candidate_words


class RegisterTarget:
    def __init__(self, dut, address=0x50):
        self.dut, self.address = dut, address
        self.memory = bytearray(range(256))
        self.pointer = 0
        self.drive_sda = self.drive_scl = False
        self.fault_sda = self.fault_scl = False
        self.changed = Event()
        self.active = False
        self.mode = "idle"
        self.last_rise = self.last_fall = None
        self.start_time = None
        self.arm()

    def arm(self, *, nack_address=None, nack_data=None, stretches=None):
        self.starts = self.stops = 0
        self.addresses, self.writes, self.host_acks = [], [], []
        self.falls = 0
        self.nack_address, self.nack_data = nack_address, nack_data
        self.stretches = dict(stretches or {})
        self.stretch_count = 0
        self.controller_drives = []

    async def release_clock(self, duration):
        await Timer(duration, unit="ns")
        self.drive_scl = False
        self.changed.set()

    def start_read(self):
        self.mode, self.bits = "read", 0
        self.byte = self.memory[self.pointer]
        self.drive_sda = not bool(self.byte & 0x80)

    def edge(self, previous, now):
        time = get_sim_time(unit="ns")
        if previous & 0x10 and now & 0x10:
            if previous & 0x20 and not now & 0x20:
                self.starts += 1
                self.start_time = time
                self.active = True
                self.mode, self.bits, self.byte = "address", 0, 0
                self.drive_sda = False
            elif not previous & 0x20 and now & 0x20:
                if self.active and self.last_rise is not None:
                    assert time - self.last_rise >= 4000, "STOP setup time"
                self.stops += 1
                self.active, self.mode, self.drive_sda = False, "idle", False
        if not previous & 0x10 and now & 0x10:
            if self.active and self.last_fall is not None:
                assert time - self.last_fall >= 4700, "I2C Standard-mode SCL low time"
            if self.active and self.last_rise is not None:
                assert time - self.last_rise >= 10_000, (
                    "I2C Standard-mode maximum SCL frequency"
                )
            self.last_rise = time
            sda = int(bool(now & 0x20))
            if self.mode in ("address", "write"):
                self.byte = (self.byte << 1) | sda
                self.bits += 1
                if self.bits == 8:
                    if self.mode == "address":
                        self.addresses.append(self.byte)
                        self.accept = (
                            self.byte >> 1 == self.address
                            and len(self.addresses) != self.nack_address
                        )
                        self.next_mode = "read" if self.byte & 1 else "write"
                        self.need_pointer = True
                    else:
                        self.writes.append(self.byte)
                        self.accept = len(self.writes) != self.nack_data
                        self.next_mode = "write"
                        if self.accept:
                            if self.need_pointer:
                                self.pointer, self.need_pointer = self.byte, False
                            else:
                                self.memory[self.pointer] = self.byte
                                self.pointer = (self.pointer + 1) & 255
                    self.mode = "ack_setup"
            elif self.mode == "ack":
                assert sda == int(not self.accept)
                self.mode = "ack_end"
            elif self.mode == "read":
                assert sda == ((self.byte >> (7 - self.bits)) & 1)
                self.bits += 1
                if self.bits == 8:
                    self.mode = "read_end"
            elif self.mode == "host_ack":
                self.host_acks.append(sda)
                self.pointer = (self.pointer + 1) & 255
                self.mode = "host_ack_end"
        elif previous & 0x10 and not now & 0x10:
            if self.active and self.last_rise is not None:
                assert time - self.last_rise >= 4000, "I2C Standard-mode SCL high time"
            if self.active and self.start_time is not None:
                assert time - self.start_time >= 4000, "START hold time"
                self.start_time = None
            self.last_fall = time
            if not self.active:
                return
            self.falls += 1
            if self.falls in self.stretches:
                self.drive_scl = True
                self.stretch_count += 1
                if self.stretches[self.falls] is not None:
                    cocotb.start_soon(self.release_clock(self.stretches[self.falls]))
            if self.mode == "ack_setup":
                self.drive_sda = self.accept
                self.mode = "ack"
            elif self.mode == "ack_end":
                self.drive_sda = False
                if not self.accept:
                    self.mode = "ignore"
                elif self.next_mode == "read":
                    self.start_read()
                else:
                    self.mode, self.bits, self.byte = "write", 0, 0
            elif self.mode == "read":
                self.drive_sda = not bool((self.byte >> (7 - self.bits)) & 1)
            elif self.mode == "read_end":
                self.drive_sda = False
                self.mode = "host_ack"
            elif self.mode == "host_ack_end":
                if self.host_acks[-1] == 0:
                    self.start_read()
                else:
                    self.mode = "ignore"

    async def run(self):
        previous = 0x30
        self.dut.uio_in.value = previous
        while True:
            for _ in range(4):
                oe, out = int(self.dut.uio_oe.value), int(self.dut.uio_out.value)
                if not self.controller_drives or self.controller_drives[-1] != oe:
                    self.controller_drives.append(oe)
                assert not oe & ~0x30, "unexpected pin drive"
                assert not oe & out, "open-drain controller drove high"
                mask = (0x20 if self.drive_sda else 0) | (0x10 if self.drive_scl else 0)
                mask |= (0x20 if self.fault_sda else 0) | (
                    0x10 if self.fault_scl else 0
                )
                now = (~(oe | mask)) & 0x30
                self.dut.uio_in.value = now
                if now == previous:
                    break
                self.edge(previous, now)
                previous = now
            else:
                raise AssertionError("open-drain model did not settle")
            self.changed.clear()
            await First(
                ValueChange(self.dut.uio_oe),
                ValueChange(self.dut.uio_out),
                self.changed.wait(),
            )
            await Timer(1, unit="ps")


async def setup(dut):
    assert os.environ.get("I2C_CAPACITY_EXPERIMENT") == "256", (
        "candidate requires explicit expanded model"
    )
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=0x30)
    await load_program(dut, candidate_words())
    peer = RegisterTarget(dut)
    cocotb.start_soon(peer.run())
    return PinController(dut, 0x493243), peer


async def transact(dut, controller, ident, payload, count, *, status=0, expected=b""):
    request = Request(
        ident, 1, arguments_length=2, input_count=len(payload), output_limit=count
    )
    await controller.submit(request, payload, bytes([0x50, count]))
    output, event = await controller.complete(request, poll_limit=100_000)
    assert output == [(byte, 0) for byte in expected]
    assert event.status == status
    assert event.detail == 0
    assert int(dut.uio_oe.value) == 0
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_i2c_candidate_write_read(dut):
    controller, peer = await setup(dut)
    rng = random.Random(0x493243)
    for ident, length in enumerate([1, 2, 63, 1]):
        register = 0x20
        data = bytes(rng.randrange(256) for _ in range(length))
        peer.arm()
        await transact(dut, controller, ident * 2, bytes([register]) + data, 0)
        assert peer.starts == peer.stops == 1
        assert peer.addresses == [0xA0]
        assert peer.writes == list(bytes([register]) + data)
        assert peer.memory[register : register + length] == data
        peer.arm()
        await transact(
            dut, controller, ident * 2 + 1, bytes([register]), length, expected=data
        )
        assert peer.starts == 2 and peer.stops == 1
        assert peer.addresses == [0xA0, 0xA1]
        assert peer.host_acks == [0] * (length - 1) + [1]
    # Read the full queue capacity, including data not prepared by this host request.
    peer.arm()
    await transact(
        dut, controller, 20, b"\x80", 64, expected=bytes(peer.memory[0x80:0xC0])
    )
    assert peer.host_acks == [0] * 63 + [1]


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_i2c_candidate_stretch_nack_recovery(dut):
    controller, peer = await setup(dut)
    for ident, options in enumerate(
        [
            {"nack_address": 1},
            {"nack_data": 1},
            {"nack_data": 2},
            {"nack_address": 2},
        ]
    ):
        peer.arm(**options)
        await transact(dut, controller, 100 + ident, b"\x20\x55\xaa", 2, status=8)
        assert peer.stops == 1
    for ident, fall in enumerate([1, 9, 10, 19, 28, 37, 45]):
        peer.arm(stretches={fall: 8_000})
        expected = bytes(peer.memory[0x20:0x22])
        await transact(dut, controller, 200 + ident, b"\x20", 2, expected=expected)
        assert peer.stretch_count == 1 and peer.stops == 1
        assert peer.host_acks == [0, 1]
    peer.arm(stretches={1: 100_000})
    await transact(dut, controller, 300, b"\x20", 1, status=9)
    await Timer(100_000, unit="ns")
    peer.arm()
    await transact(
        dut, controller, 301, b"\x20", 1, expected=bytes([peer.memory[0x20]])
    )
    assert peer.host_acks == [1] and peer.stops == 1


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_i2c_candidate_timeout_phases(dut):
    controller, peer = await setup(dut)
    # Hold SCL beyond the configured polling bound at TX data/ACK, repeated
    # START, read-address ACK, RX ACK/data, and STOP. Expect preserved partial
    # bytes only after all eight data bits have been sampled.
    for ident, (fall, received) in enumerate(
        [(1, 0), (9, 0), (19, 0), (28, 0), (37, 1), (38, 1), (47, 2)]
    ):
        peer.arm(stretches={fall: 100_000})
        expected = bytes(peer.memory[0x20 : 0x20 + received])
        await transact(
            dut, controller, 400 + ident * 2, b"\x20", 2, expected=expected, status=9
        )
        assert peer.stretch_count == 1
        await Timer(100_000, unit="ns")
        peer.arm()
        await transact(
            dut,
            controller,
            401 + ident * 2,
            b"\x20",
            1,
            expected=bytes([peer.memory[0x20]]),
        )
        assert peer.host_acks == [1] and peer.stops == 1


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_i2c_candidate_permanent_clock_fault(dut):
    controller, peer = await setup(dut)
    for ident, fall in enumerate([1, 9]):
        peer.arm(stretches={fall: None})
        started = get_sim_time(unit="ns")
        await transact(dut, controller, 600 + ident * 4, b"\x20", 1, status=9)
        assert get_sim_time(unit="ns") - started < 2_000_000, "unbounded recovery"
        peer.arm()
        await transact(dut, controller, 601 + ident * 4, b"\x20", 1, status=9)
        assert all(oe == 0 for oe in peer.controller_drives)
        peer.drive_scl = False
        peer.changed.set()
        await Timer(1000, unit="ns")
        if fall == 9:
            # After permanent SCL loss during ACK, the target still holds SDA.
            # The first retry clears the old transfer and reports TIMEOUT;
            # it does not silently replay the newly submitted transaction.
            peer.arm()
            await transact(dut, controller, 602 + ident * 4, b"\x20", 1, status=9)
            assert peer.stops == 1
        peer.arm()
        await transact(
            dut,
            controller,
            603 + ident * 4,
            b"\x20",
            1,
            expected=bytes([peer.memory[0x20]]),
        )
        assert peer.host_acks == [1] and peer.stops == 1


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_i2c_candidate_busy_bus(dut):
    controller, peer = await setup(dut)
    for ident, wire in enumerate(["fault_sda", "fault_scl"]):
        setattr(peer, wire, True)
        peer.changed.set()
        await Timer(1000, unit="ns")
        peer.arm()
        await transact(dut, controller, 500 + ident * 2, b"\x20", 1, status=9)
        assert all(oe == 0 for oe in peer.controller_drives), (
            "busy bus must remain released"
        )
        setattr(peer, wire, False)
        peer.changed.set()
        await Timer(1000, unit="ns")
        peer.arm()
        await transact(
            dut,
            controller,
            501 + ident * 2,
            b"\x20",
            1,
            expected=bytes([peer.memory[0x20]]),
        )
        assert peer.host_acks == [1] and peer.stops == 1
