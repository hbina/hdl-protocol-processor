"""Standalone sequential 8N1 echo: receive -> RAM[0] -> transmit -> rearm."""

from __future__ import annotations
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.assembler import assemble_image
from tools.program import Image


def generate(*, clock_hz: int = 50_000_000, baud: int = 1_000_000) -> Image:
    """Sender must wait for READY=uio2 and send only one frame at a time."""
    if clock_hz <= 0 or baud <= 0:
        raise ValueError("clock and baud must be positive")
    period = (clock_hz + baud // 2) // baud
    if period < 50:
        raise ValueError("UART requires at least 50 processor clocks per bit")
    if abs(clock_hz / period / baud - 1) > 0.01:
        raise ValueError("rounded baud differs from requested baud by more than 1%")
    lines = [
        f"# Sequential 8N1 echo: clock={clock_hz}, baud={baud}, bit_clocks={period}.",
        "# RX=uio1, TX=uio0, READY=uio2, VALID=uio3; false/frame=uio4/5.",
        "# RAM[0]=last RX/staged TX; [241]=false starts, [242]=framing errors.",
        "# READY is low during RX/TX/rearm. Traffic sent while busy is unsupported.",
    ]

    def emit(text: str) -> None:
        lines.extend(text.strip().splitlines())

    def delay(clocks: int) -> None:
        while clocks:
            span = min(clocks, 256)
            lines.append(f"WAIT {span - 1}")
            clocks -= span

    emit(
        "LDI r0, 1\nOUT r0, 0\nLDI r1, 61\nOE r1, 0\nLDI r0, 0\nOUT r0, 1\nLDI r2, 0\nSTORE r0, r2\nLDI r2, 241\nSTORE r0, r2\nADDI r2, 1\nSTORE r0, r2\narm:\nWAITPIN 1, 1"
    )
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
        "LDI r1, 1\nOUTBIT r1, 2\nstart:\nWAITPIN 1, 0\nLDI r1, 0\nOUTBIT r1, 2\nOUTBIT r1, 3"
    )
    delay(period // 2 - 4)
    emit(
        "INBIT r1, 1\nJZ r1, start_valid\nJMP false_start\nstart_valid:\nLDI r0, 0\nLDI r2, 8"
    )
    delay(period - 4)
    emit("rx_data:\nINBIT r1, 1\nSHR r0\nROR r1\nOR r0, r1")
    delay(period - 5)
    emit(
        "DJNZ r2, rx_data\nINBIT r1, 1\nJZ r1, framing_error\nLDI r3, 0\nSTORE r0, r3\nOUT r0, 1\nOUTBIT r1, 3\nLDI r0, 0\nOUTBIT r0, 0\nLOAD r0, r3\nLDI r2, 8\nLDI r1, 1"
    )
    delay(period - 5)
    emit("tx_data:\nOUTBIT r0, 0\nSHR r0")
    delay(period - 3)
    emit("DJNZ r2, tx_data\nOUTBIT r1, 0")
    delay(period - 2)
    emit("JMP arm")
    for label, pin, address in [("false_start", 4, 241), ("framing_error", 5, 242)]:
        emit(
            f"{label}:\nLDI r1, 1\nOUTBIT r1, {pin}\nLDI r2, {address}\nLOAD r1, r2\nADDI r1, 1\nSTORE r1, r2\nJMP arm"
        )
    return assemble_image("\n".join(lines) + "\n")


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
