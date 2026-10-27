"""Standalone continuous 8N1 receiver with a bounded, drop-new RAM buffer."""

from __future__ import annotations
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.assembler import assemble_image
from tools.program import Image


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
    lines = [
        f"# 8N1 RX: clock={clock_hz}, baud={baud}, bit_clocks={period}.",
        f"# RAM[0..{capacity - 1}] keeps first {capacity} bytes; full buffer drops new bytes.",
        "# RAM[241]=false starts, [242]=framing errors, [243]=drops (modulo 256).",
    ]

    def emit(text: str) -> None:
        lines.extend(text.strip().splitlines())

    def delay(clocks: int) -> None:
        while clocks:
            span = min(clocks, 256)
            lines.append(f"WAIT {span - 1}")
            clocks -= span

    emit("LDI r0, 0\nOUT r0, 0\nOUT r0, 1\nLDI r1, 252\nOE r1, 0\nLDI r2, 241")
    for _ in range(3):
        emit("STORE r0, r2\nADDI r2, 1")
    emit("LDI r3, 0\narm:\nWAITPIN 1, 1")
    # Require a sampled idle interval after boot or errors, never between good
    # consecutive frames. Every qualifying sample is separated by three clocks.
    samples = (period + 2) // 3 + 1
    block = 0
    while samples:
        count = min(samples, 255)
        emit(
            f"LDI r2, {count}\nidle_{block}:\nINBIT r1, 1\nJZ r1, arm\nDJNZ r2, idle_{block}"
        )
        samples -= count
        block += 1
    emit(
        "LDI r1, 1\nready:\nOUTBIT r1, 2\nstart:\nWAITPIN 1, 0\nLDI r1, 0\nOUTBIT r1, 2\nOUTBIT r1, 3"
    )
    delay(period // 2 - 4)
    emit(
        "INBIT r1, 1\nJZ r1, start_valid\nJMP false_start\nstart_valid:\nLDI r0, 0\nLDI r2, 8"
    )
    delay(period - 4)
    emit("data:\nINBIT r1, 1\nSHR r0\nROR r1\nOR r0, r1")
    delay(period - 5)
    emit(
        f"DJNZ r2, data\nINBIT r1, 1\nJZ r1, framing_error\nCMPLTI r3, {capacity}\nJFAIL overflow\nSTORE r0, r3\nADDI r3, 1\nOUT r0, 1\nOUTBIT r1, 3\nCMPI r3, {capacity}\nJFAIL ready\nOUTBIT r1, 7\nJMP ready"
    )
    # On a good stop bit r1=1, so the fast non-full path reaches the next
    # start wait within 12 clocks. Slow-path counters never touch payload RAM.
    for label, pin, address, resume in [
        ("false_start", 4, 241, "arm"),
        ("framing_error", 5, 242, "arm"),
    ]:
        emit(
            f"{label}:\nLDI r1, 1\nOUTBIT r1, {pin}\nLDI r2, {address}\nLOAD r1, r2\nADDI r1, 1\nSTORE r1, r2\nJMP {resume}"
        )
    emit(
        "overflow:\nOUTBIT r1, 6\nLDI r2, 243\nLOAD r1, r2\nADDI r1, 1\nSTORE r1, r2\nLDI r1, 1\nJMP ready"
    )
    return assemble_image("\n".join(lines) + "\n")


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
