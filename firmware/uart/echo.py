"""Standalone sequential 8N1 echo: receive -> RAM[0] -> transmit -> rearm."""

from __future__ import annotations
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.isa import (
    ADDI,
    DJNZ,
    INBIT,
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


def generate(*, clock_hz: int = 50_000_000, baud: int = 1_000_000) -> Image:
    """Sender must wait for READY=uio2 and send only one frame at a time."""
    if clock_hz <= 0 or baud <= 0:
        raise ValueError("clock and baud must be positive")
    period = (clock_hz + baud // 2) // baud
    if period < 50:
        raise ValueError("UART requires at least 50 processor clocks per bit")
    if abs(clock_hz / period / baud - 1) > 0.01:
        raise ValueError("rounded baud differs from requested baud by more than 1%")
    arm = Label("arm")
    false_start = Label("false_start")
    framing_error = Label("framing_error")
    rx_data = Label("rx_data")
    start = Label("start")
    start_valid = Label("start_valid")
    tx_data = Label("tx_data")
    program = Program(
        [
            Comment(
                f"Sequential 8N1 echo: clock={clock_hz}, baud={baud}, bit_clocks={period}."
            ),
            Comment("RX=uio1, TX=uio0, READY=uio2, VALID=uio3; false/frame=uio4/5."),
            Comment(
                "RAM[0]=last RX/staged TX; [241]=false starts, [242]=framing errors."
            ),
            Comment(
                "READY is low during RX/TX/rearm. Traffic sent while busy is unsupported."
            ),
        ]
    )

    def delay(clocks: int) -> None:
        while clocks:
            span = min(clocks, 256)
            program.add(WAIT(span - 1))
            clocks -= span

    program.extend(
        [
            LDI(r0, 1),
            OUT(r0, 0),
            LDI(r1, 61),
            OE(r1, 0),
            LDI(r0, 0),
            OUT(r0, 1),
            LDI(r2, 0),
            STORE(r0, r2),
            LDI(r2, 241),
            STORE(r0, r2),
            ADDI(r2, 1),
            STORE(r0, r2),
            arm,
            WAITPIN(1, 1),
        ]
    )
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
    program.extend([rx_data, INBIT(r1, 1), SHR(r0), ROR(r1), OR(r0, r1)])
    delay(period - 5)
    program.extend(
        [
            DJNZ(r2, rx_data),
            INBIT(r1, 1),
            JZ(r1, framing_error),
            LDI(r3, 0),
            STORE(r0, r3),
            OUT(r0, 1),
            OUTBIT(r1, 3),
            LDI(r0, 0),
            OUTBIT(r0, 0),
            LOAD(r0, r3),
            LDI(r2, 8),
            LDI(r1, 1),
        ]
    )
    delay(period - 5)
    program.extend([tx_data, OUTBIT(r0, 0), SHR(r0)])
    delay(period - 3)
    program.extend([DJNZ(r2, tx_data), OUTBIT(r1, 0)])
    delay(period - 2)
    program.extend([JMP(arm)])
    for label, pin, address in [(false_start, 4, 241), (framing_error, 5, 242)]:
        program.extend(
            [
                label,
                LDI(r1, 1),
                OUTBIT(r1, pin),
                LDI(r2, address),
                LOAD(r1, r2),
                ADDI(r1, 1),
                STORE(r1, r2),
                JMP(arm),
            ]
        )
    return program.link()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clock-hz", type=int, default=50_000_000)
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        image = generate(clock_hz=args.clock_hz, baud=args.baud)
    except ValueError as error:
        parser.error(str(error))
    text = image.disassemble()
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
