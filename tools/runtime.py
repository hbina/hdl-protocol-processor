"""Firmware ABI v1 and asynchronous byte-transport controller.

The token exchange callback owns physical GPIO timing. It receives a six-bit
token and returns the six-bit response after request/acknowledgement completes,
or raises TransportError/TimeoutError. Timeouts require reset/reload; writes
must never be blindly retried.
"""

from __future__ import annotations

from dataclasses import dataclass
from asyncio import CancelledError
import struct
from collections.abc import Awaitable, Callable

RECORD = struct.Struct("<HBBHHHH4s")
EVENT = struct.Struct("<HBBHHH6s")


class TransportError(RuntimeError):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f"runtime transport error {code}")


@dataclass(frozen=True)
class Request:
    request_id: int
    operation: int
    arguments_address: int = 0
    arguments_length: int = 0
    input_count: int = 0
    output_limit: int = 0
    flags: int = 0

    def encode(self) -> bytes:
        return RECORD.pack(
            self.request_id,
            self.operation,
            self.flags,
            self.arguments_address,
            self.arguments_length,
            self.input_count,
            self.output_limit,
            bytes(4),
        )


@dataclass(frozen=True)
class Completion:
    request_id: int
    kind: int
    status: int
    input_consumed: int
    output_produced: int
    detail: int

    @classmethod
    def decode(cls, record: bytes) -> Completion:
        fields = EVENT.unpack(record)
        if fields[-1] != bytes(6) or fields[1] != 1:
            raise ValueError("invalid terminal event")
        return cls(*fields[:-1])


class RuntimeController:
    def __init__(self, exchange: Callable[[int], Awaitable[int]]):
        self.exchange = exchange
        self.outstanding = False
        self.failed = False

    async def _token(self, value: int) -> int:
        if self.failed:
            raise RuntimeError("transport failed; reset/reload and replace controller")
        try:
            return await self.exchange(value)
        except (TimeoutError, OSError, CancelledError):
            self.failed = True
            raise

    async def _address(self, operation: int, address: int) -> int:
        if not 0 <= address <= 0xFFFF:
            raise ValueError("address out of range")
        await self._token(operation)
        await self._token(address & 63)
        await self._token((address >> 6) & 63)
        return await self._token(address >> 12)

    async def read(self, address: int) -> int:
        low = await self._address(0, address)
        high = await self._token(0)
        return low | (high << 6)

    async def write(self, address: int, value: int) -> None:
        if not 0 <= value <= 255:
            raise ValueError("byte out of range")
        await self._address(1, address)
        await self._token(value & 63)
        await self._token(value >> 6)

    async def capabilities(self) -> dict[str, int]:
        names = (
            "version",
            "program_words",
            "payload_depth",
            "record_bytes",
            "parameter_bytes",
        )
        return {name: await self.read(0x106 + i) for i, name in enumerate(names)}

    async def submit(
        self, request: Request, payload: bytes, arguments: bytes = b""
    ) -> None:
        record = request.encode()  # Validate widths before modifying hardware.
        if self.outstanding:
            raise RuntimeError("one request is already outstanding")
        if len(payload) != request.input_count or len(payload) > 64:
            raise ValueError("payload must match input_count and fit 64 entries")
        if not 0 <= request.output_limit <= 64:
            raise ValueError("output limit out of range")
        if len(arguments) != request.arguments_length:
            raise ValueError("argument length mismatch")
        if request.arguments_address + len(arguments) > 128:
            raise ValueError("arguments must fit parameter memory")
        # Claim ownership before the first await, including the idle check.
        # Timeout during that read can leave a partial transport transaction.
        self.outstanding = True
        if await self.read(0x101) != 0:
            raise RuntimeError("runtime channel is not empty and idle")
        await self.write(0x100, 1)  # Clear any idle partial record staging.
        for i, value in enumerate(arguments):
            await self.write(request.arguments_address + i, value)
        for value in payload:
            await self.write(0x110, value)
        for value in record:
            await self.write(0x120, value)
        await self.write(0x121, 0)

    async def complete(
        self, request: Request, *, poll_limit: int = 10000
    ) -> tuple[list[tuple[int, int]], Completion]:
        if not self.outstanding:
            raise RuntimeError("no outstanding request")
        for _ in range(poll_limit):
            if await self.read(0x105):
                break
        else:
            self.failed = True
            raise TimeoutError(
                "firmware did not publish an event; reset/reload required"
            )
        output = []
        for _ in range(await self.read(0x103)):
            output.append((await self.read(0x133), await self.read(0x134)))
            await self.write(0x135, 0)
        event = Completion.decode(bytes([await self.read(0x142) for _ in range(16)]))
        if event.request_id != request.request_id:
            raise ValueError("completion request ID mismatch")
        if (
            event.input_consumed != request.input_count
            or event.output_produced != len(output)
            or event.output_produced > request.output_limit
        ):
            raise ValueError("completion count mismatch")
        self.outstanding = False
        return output, event
