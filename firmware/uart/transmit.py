"""Standalone RAM-backed repeating 8N1 transmitter; no experiment dependencies."""

from __future__ import annotations
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.isa import (
    ADDI,
    CMPI,
    DJNZ,
    JFAIL,
    JMP,
    LDI,
    LOAD,
    Label,
    NOP,
    OEBIT,
    OUTBIT,
    SHR,
    STORE,
    WAIT,
    r0,
    r1,
    r2,
    r3,
)
from tools.program import Comment, Image, Program


def generate(
    *,
    clock_hz: int = 50_000_000,
    baud: int = 1_000_000,
    payload: bytes = b"\x00\xa5\xff\x55",
    tx_pin: int = 0,
) -> Image:
    """Initialize RAM[0:len(payload)] then repeat it with exactly one stop bit."""
    if clock_hz <= 0 or baud <= 0:
        raise ValueError("clock and baud must be positive")
    period = (clock_hz + baud // 2) // baud
    if period < 50:
        raise ValueError("UART requires at least 50 processor clocks per bit")
    if abs(clock_hz / period / baud - 1) > 0.01:
        raise ValueError("rounded baud differs from requested baud by more than 1%")
    if not 1 <= len(payload) <= 64:
        raise ValueError("payload must contain 1..64 bytes")
    if not 0 <= tx_pin < 8:
        raise ValueError("TX must use a bidirectional output pin 0..7")
    data = Label("data")
    frame = Label("frame")
    next_frame = Label("next_frame")
    no_wrap = Label("no_wrap")
    program = Program(
        [
            Comment(
                f"8N1 RAM transmitter: clock={clock_hz}, baud={baud}, bit_clocks={period}."
            ),
            Comment(
                "Payload is initialized by firmware, then repeated without reload."
            ),
            LDI(r1, 0),
        ]
    )

    def delay(clocks: int) -> None:
        while clocks:
            span = min(clocks, 256)
            program.add(WAIT(span - 1))
            clocks -= span

    for byte in payload:
        program.extend([LDI(r0, byte), STORE(r0, r1), ADDI(r1, 1)])
    program.extend([LDI(r3, 1), OUTBIT(r3, tx_pin), OEBIT(r3, tx_pin), LDI(r1, 0)])
    delay(period)
    program.extend(
        [
            frame,
            LDI(r0, 0),
            OUTBIT(r0, tx_pin),
            LOAD(r0, r1),
            LDI(r2, 8),
            LDI(r3, 1),
        ]
    )
    delay(period - 5)
    program.extend([data, OUTBIT(r0, tx_pin), SHR(r0)])
    delay(period - 3)
    program.extend(
        [
            DJNZ(r2, data),
            OUTBIT(r3, tx_pin),
            ADDI(r1, 1),
            CMPI(r1, len(payload)),
            JFAIL(no_wrap),
            LDI(r1, 0),
            JMP(next_frame),
            no_wrap,
            NOP(),
            NOP(),
            next_frame,
        ]
    )
    delay(period - 8)
    program.extend([JMP(frame)])
    return program.link()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clock-hz", type=int, default=50_000_000)
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--payload-hex", default="00a5ff55")
    parser.add_argument("--tx-pin", type=int, default=0)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        image = generate(
            clock_hz=args.clock_hz,
            baud=args.baud,
            payload=bytes.fromhex(args.payload_hex),
            tx_pin=args.tx_pin,
        )
    except ValueError as error:
        parser.error(str(error))
    text = image.disassemble()
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
