"""Standalone continuous 8N1 receiver with a bounded, drop-new RAM buffer."""

from __future__ import annotations
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.isa import (
    ADDI,
    CMPI,
    CMPLTI,
    DJNZ,
    INBIT,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    OE,
    OR,
    OUT,
    OUTBIT,
    ROR,
    SHR,
    STORE,
    WAIT,
    WAITPIN,
    r0,
    r1,
    r2,
    r3,
)
from tools.program import Comment, Image, Program


def generate(
    *, clock_hz: int = 50_000_000, baud: int = 1_000_000, capacity: int = 128
) -> Image:
    """RX=uio1; READY/VALID/errors/FULL=uio2..7; last accepted byte=uo."""
    if clock_hz <= 0 or baud <= 0:
        raise ValueError("clock and baud must be positive")
    period = (clock_hz + baud // 2) // baud
    if period < 50:
        raise ValueError("UART requires at least 50 processor clocks per bit")
    if abs(clock_hz / period / baud - 1) > 0.01:
        raise ValueError("rounded baud differs from requested baud by more than 1%")
    if not 1 <= capacity <= 240:
        raise ValueError("RX capacity must be 1..240 bytes")
    arm = Label("arm")
    data = Label("data")
    false_start = Label("false_start")
    framing_error = Label("framing_error")
    overflow = Label("overflow")
    ready = Label("ready")
    start = Label("start")
    start_valid = Label("start_valid")
    program = Program(
        [
            Comment(f"8N1 RX: clock={clock_hz}, baud={baud}, bit_clocks={period}."),
            Comment(
                f"RAM[0..{capacity - 1}] keeps first {capacity} bytes; full buffer drops new bytes."
            ),
            Comment(
                "RAM[241]=false starts, [242]=framing errors, [243]=drops (modulo 256)."
            ),
        ]
    )

    def delay(clocks: int) -> None:
        while clocks:
            span = min(clocks, 256)
            program.add(WAIT(span - 1))
            clocks -= span

    program.extend(
        [LDI(r0, 0), OUT(r0, 0), OUT(r0, 1), LDI(r1, 252), OE(r1, 0), LDI(r2, 241)]
    )
    for _ in range(3):
        program.extend([STORE(r0, r2), ADDI(r2, 1)])
    program.extend([LDI(r3, 0), arm, WAITPIN(1, 1)])
    # Require a sampled idle interval after boot or errors, never between good
    # consecutive frames. Every qualifying sample is separated by three clocks.
    samples = (period + 2) // 3 + 1
    block = 0
    while samples:
        count = min(samples, 255)
        idle = Label(f"idle_{block}")
        program.extend(
            [
                LDI(r2, count),
                idle,
                INBIT(r1, 1),
                JZ(r1, arm),
                DJNZ(r2, idle),
            ]
        )
        samples -= count
        block += 1
    program.extend(
        [
            LDI(r1, 1),
            ready,
            OUTBIT(r1, 2),
            start,
            WAITPIN(1, 0),
            LDI(r1, 0),
            OUTBIT(r1, 2),
            OUTBIT(r1, 3),
        ]
    )
    delay(period // 2 - 4)
    program.extend(
        [
            INBIT(r1, 1),
            JZ(r1, start_valid),
            JMP(false_start),
            start_valid,
            LDI(r0, 0),
            LDI(r2, 8),
        ]
    )
    delay(period - 4)
    program.extend([data, INBIT(r1, 1), SHR(r0), ROR(r1), OR(r0, r1)])
    delay(period - 5)
    program.extend(
        [
            DJNZ(r2, data),
            INBIT(r1, 1),
            JZ(r1, framing_error),
            CMPLTI(r3, capacity),
            JFAIL(overflow),
            STORE(r0, r3),
            ADDI(r3, 1),
            OUT(r0, 1),
            OUTBIT(r1, 3),
            CMPI(r3, capacity),
            JFAIL(ready),
            OUTBIT(r1, 7),
            JMP(ready),
        ]
    )
    # On a good stop bit r1=1, so the fast non-full path reaches the next
    # start wait within 12 clocks. Slow-path counters never touch payload RAM.
    for label, pin, address, resume in [
        (false_start, 4, 241, arm),
        (framing_error, 5, 242, arm),
    ]:
        program.extend(
            [
                label,
                LDI(r1, 1),
                OUTBIT(r1, pin),
                LDI(r2, address),
                LOAD(r1, r2),
                ADDI(r1, 1),
                STORE(r1, r2),
                JMP(resume),
            ]
        )
    program.extend(
        [
            overflow,
            OUTBIT(r1, 6),
            LDI(r2, 243),
            LOAD(r1, r2),
            ADDI(r1, 1),
            STORE(r1, r2),
            LDI(r1, 1),
            JMP(ready),
        ]
    )
    return program.link()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clock-hz", type=int, default=50_000_000)
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--capacity", type=int, default=128)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        image = generate(clock_hz=args.clock_hz, baud=args.baud, capacity=args.capacity)
    except ValueError as error:
        parser.error(str(error))
    text = image.disassemble()
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
