import asyncio
from unittest.mock import AsyncMock

import pytest

from tools.runtime import EVENT, Request, RuntimeController


def test_request_wire_byte_order():
    request = Request(0xABCD, 2, 0x4567, 0x0123, 0x5678, 0x9ABC)
    assert request.encode() == bytes.fromhex("cdab0200674523017856bc9a00000000")


def test_timeout_during_idle_check_requires_reset_and_never_retries():
    calls = []

    async def exchange(token):
        calls.append(token)
        if len(calls) == 2:
            raise TimeoutError("lost acknowledgement")
        return 0

    async def exercise():
        controller = RuntimeController(exchange)
        with pytest.raises(TimeoutError):
            await controller.submit(Request(1, 1), b"")
        assert controller.failed and controller.outstanding
        with pytest.raises(RuntimeError):
            await controller.submit(Request(1, 1), b"")
        with pytest.raises(RuntimeError):
            await controller.read(0x106)
        assert calls == [0, 1]

    asyncio.run(exercise())


def test_completion_cannot_exceed_requested_output_limit():
    async def exercise():
        controller = RuntimeController(AsyncMock())
        controller.outstanding = True
        record = EVENT.pack(42, 1, 0, 0, 3, 0, bytes(6))
        controller.read = AsyncMock(side_effect=[1, 3, 11, 0, 22, 0, 33, 0, *record])
        controller.write = AsyncMock()
        with pytest.raises(ValueError, match="count mismatch"):
            await controller.complete(Request(42, 1, output_limit=2))
        assert controller.outstanding
        assert controller.write.await_count == 3

    asyncio.run(exercise())


def test_wait_for_timeout_cannot_leave_transport_reusable():
    async def exercise():
        entered = asyncio.Event()
        calls = []

        async def exchange(token):
            calls.append(token)
            if len(calls) == 2:
                entered.set()
                await asyncio.Future()  # Wait for the missing acknowledgement.
            return 0

        controller = RuntimeController(exchange)
        transfer = asyncio.create_task(controller.submit(Request(1, 1), b""))
        await entered.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(transfer, timeout=0.01)
        assert controller.failed and controller.outstanding
        with pytest.raises(RuntimeError):
            await controller.read(0x106)
        assert calls == [0, 1]

    asyncio.run(exercise())
