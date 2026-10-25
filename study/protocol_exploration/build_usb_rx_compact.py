#!/usr/bin/env python3
"""Try a firmware-only USB decoder optimization before changing architecture.

Pack previous line state and consecutive-one count in r2, keeping the decoded
byte in r3. This removes per-bit RAM spills. Capture/CRC/ACK remain identical
to the buffered baseline; this is not claimed to solve the response deadline.
"""

from pathlib import Path

from build_usb_rx import generate as baseline_source
from tools.isa import (
    ADDI,
    ANDI,
    CMPI,
    CMPLTI,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    OR,
    ROR,
    STORE,
    XOR,
    r0,
    r1,
    r2,
    r3,
)
from tools.program import Comment


def generate():
    source = baseline_source()
    prefix, rest = source.split([Label("decode")], 1)
    _old_decoder, suffix = rest.split([Label("aligned")], 1)
    decoder = [
        Label("decode"),
        LDI(r1, 250),
        LOAD(r0, r1),
        CMPI(r0, 144),
        JFAIL(Label("decode_nonempty")),
        JMP(Label("form_error")),
        Label("decode_nonempty"),
        LDI(r0, 8),
        LDI(r1, 251),
        STORE(r0, r1),
        LDI(r0, 144),
        LDI(r1, 253),
        STORE(r0, r1),
        ADDI(r1, 1),
        STORE(r0, r1),
        Comment("r2=2*run_length+previous_VP; SYNC ends inK with run_length1."),
        LDI(r2, 3),
        LDI(r3, 0),
        Label("raw_bit"),
        LDI(r1, 254),
        LOAD(r1, r1),
        LOAD(r0, r1),
        CMPI(r0, 3),
        JFAIL(Label("line_valid")),
        JMP(Label("form_error")),
        Label("line_valid"),
        ANDI(r0, 1),
        MOV(r1, r2),
        XOR(r1, r0),
        ANDI(r1, 1),
        CMPI(r1, 0),
        ANDI(r2, 254),
        OR(r2, r0),
        JFAIL(Label("decoded_zero")),
        LDI(r0, 1),
        JMP(Label("decoded_bit")),
        Label("decoded_zero"),
        LDI(r0, 0),
        Label("decoded_bit"),
        CMPLTI(r2, 12),
        JFAIL(Label("must_stuff")),
        JZ(r0, Label("zero_bit")),
        ADDI(r2, 2),
        JMP(Label("append_bit")),
        Label("zero_bit"),
        ANDI(r2, 1),
        Label("append_bit"),
        ROR(r3),
        ANDI(r3, 127),
        ROR(r0),
        OR(r3, r0),
        LDI(r1, 251),
        LOAD(r0, r1),
        ADDI(r0, 255),
        STORE(r0, r1),
        JZ(r0, Label("byte_full")),
        JMP(Label("next_raw")),
        Label("must_stuff"),
        JZ(r0, Label("stuff_ok")),
        JMP(Label("stuff_error")),
        Label("stuff_ok"),
        ANDI(r2, 1),
        JMP(Label("next_raw")),
        Label("byte_full"),
        LDI(r1, 253),
        LOAD(r1, r1),
        STORE(r3, r1),
        ADDI(r1, 1),
        MOV(r0, r1),
        LDI(r1, 253),
        STORE(r0, r1),
        LDI(r1, 251),
        LDI(r0, 8),
        STORE(r0, r1),
        Label("next_raw"),
        LDI(r1, 254),
        LOAD(r0, r1),
        ADDI(r0, 1),
        STORE(r0, r1),
        LDI(r1, 250),
        LOAD(r1, r1),
        XOR(r0, r1),
        JZ(r0, Label("packet_end")),
        JMP(Label("raw_bit")),
        Label("packet_end"),
        CMPLTI(r2, 12),
        JFAIL(Label("stuff_error")),
        JMP(Label("aligned")),
    ]
    return (
        [Comment("Firmware-only compact decoder variant; see build_usb_rx_compact.py.")]
        + prefix
        + decoder
        + [Label("aligned")]
        + suffix
    )


if __name__ == "__main__":
    Path(__file__).with_name("usb_rx_compact_candidate.asm").write_text(
        generate().to_asm()
    )
