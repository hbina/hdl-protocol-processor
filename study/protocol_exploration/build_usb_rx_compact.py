#!/usr/bin/env python3
"""Try a firmware-only USB decoder optimization before changing architecture.

Pack previous line state and consecutive-one count in r2, keeping the decoded
byte in r3. This removes per-bit RAM spills. Capture/CRC/ACK remain identical
to the buffered baseline; this is not claimed to solve the response deadline.
"""

from pathlib import Path

from build_usb_rx import generate as baseline_source


def generate():
    source = baseline_source()
    prefix, rest = source.split("decode:\n", 1)
    _old_decoder, suffix = rest.split("aligned:\n", 1)
    decoder = """
decode:
    LDI r1, 250
    LOAD r0, r1
    CMPI r0, 144
    JFAIL decode_nonempty
    JMP form_error
decode_nonempty:
    LDI r0, 8
    LDI r1, 251
    STORE r0, r1
    LDI r0, 144
    LDI r1, 253
    STORE r0, r1
    ADDI r1, 1
    STORE r0, r1
    # r2=2*run_length+previous_VP; SYNC ends inK with run_length1.
    LDI r2, 3
    LDI r3, 0
raw_bit:
    LDI r1, 254
    LOAD r1, r1
    LOAD r0, r1
    CMPI r0, 3
    JFAIL line_valid
    JMP form_error
line_valid:
    ANDI r0, 1
    MOV r1, r2
    XOR r1, r0
    ANDI r1, 1
    CMPI r1, 0
    ANDI r2, 254
    OR r2, r0
    JFAIL decoded_zero
    LDI r0, 1
    JMP decoded_bit
decoded_zero:
    LDI r0, 0
decoded_bit:
    CMPLTI r2, 12
    JFAIL must_stuff
    JZ r0, zero_bit
    ADDI r2, 2
    JMP append_bit
zero_bit:
    ANDI r2, 1
append_bit:
    ROR r3
    ANDI r3, 127
    ROR r0
    OR r3, r0
    LDI r1, 251
    LOAD r0, r1
    ADDI r0, 255
    STORE r0, r1
    JZ r0, byte_full
    JMP next_raw
must_stuff:
    JZ r0, stuff_ok
    JMP stuff_error
stuff_ok:
    ANDI r2, 1
    JMP next_raw
byte_full:
    LDI r1, 253
    LOAD r1, r1
    STORE r3, r1
    ADDI r1, 1
    MOV r0, r1
    LDI r1, 253
    STORE r0, r1
    LDI r1, 251
    LDI r0, 8
    STORE r0, r1
next_raw:
    LDI r1, 254
    LOAD r0, r1
    ADDI r0, 1
    STORE r0, r1
    LDI r1, 250
    LOAD r1, r1
    XOR r0, r1
    JZ r0, packet_end
    JMP raw_bit
packet_end:
    CMPLTI r2, 12
    JFAIL stuff_error
    JMP aligned
"""
    decoder = (
        "\n".join(line.strip() for line in decoder.splitlines() if line.strip()) + "\n"
    )
    return (
        "# Firmware-only compact decoder variant; see build_usb_rx_compact.py.\n"
        + prefix
        + decoder
        + "aligned:\n"
        + suffix
    )


if __name__ == "__main__":
    Path(__file__).with_name("usb_rx_compact_candidate.asm").write_text(generate())
