"""Standalone RAM-backed repeating 8N1 transmitter; no experiment dependencies."""

from __future__ import annotations
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.assembler import assemble_image
from tools.program import Image


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
    lines = [
        f"# 8N1 RAM transmitter: clock={clock_hz}, baud={baud}, bit_clocks={period}.",
        "# Payload is initialized by firmware, then repeated without reload.",
        "LDI r1, 0",
    ]

    def emit(text: str) -> None:
        lines.extend(text.strip().splitlines())

    def delay(clocks: int) -> None:
        while clocks:
            span = min(clocks, 256)
            lines.append(f"WAIT {span - 1}")
            clocks -= span

    for byte in payload:
        emit(f"LDI r0, {byte}\nSTORE r0, r1\nADDI r1, 1")
    emit(f"LDI r3, 1\nOUTBIT r3, {tx_pin}\nOEBIT r3, {tx_pin}\nLDI r1, 0")
    delay(period)
    emit(f"frame:\nLDI r0, 0\nOUTBIT r0, {tx_pin}\nLOAD r0, r1\nLDI r2, 8\nLDI r3, 1")
    delay(period - 5)
    emit(f"data:\nOUTBIT r0, {tx_pin}\nSHR r0")
    delay(period - 3)
    emit(
        f"DJNZ r2, data\nOUTBIT r3, {tx_pin}\nADDI r1, 1\nCMPI r1, {len(payload)}\nJFAIL no_wrap\nLDI r1, 0\nJMP next_frame\nno_wrap:\nNOP\nNOP\nnext_frame:"
    )
    delay(period - 8)
    emit("JMP frame")
    return assemble_image("\n".join(lines) + "\n")


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
