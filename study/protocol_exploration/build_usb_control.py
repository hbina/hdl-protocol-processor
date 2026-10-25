#!/usr/bin/env python3
"""Autonomous single-packet vendor control write/read pair, generic ISA only."""

from pathlib import Path

from build_usb_stream import generate as stream_source
from tools.program import Program
from tools.isa import (
    ADDI,
    ANDI,
    CMPI,
    CMPLTI,
    DJNZ,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    ORI,
    PWRITE,
    STORE,
    WAIT,
    XOR,
    r0,
    r1,
    r2,
    r3,
    r4,
    r5,
    r6,
    r7,
)


def generate():
    source = stream_source().replace(
        [LDI(r0, 16), STORE(r0, r4)], [LDI(r0, 32), STORE(r0, r4)]
    )
    old = [LDI(r0, 40), LOAD(r0, r0), JZ(r0, Label("rearm")), JMP(Label("prepare_tx"))]
    assert source.count(old) == 1
    source = source.replace(
        old,
        [
            LDI(r0, 171),
            LDI(r1, 0),
            STORE(r1, r0),
            ADDI(r0, 1),
            STORE(r1, r0),
            JMP(Label("rearm")),
        ],
    )
    source = source.replace(
        [Label("tx_packet"), LDI(r0, 185), LDI(r1, 1), STORE(r1, r0)],
        [Label("tx_packet"), LDI(r0, 171), LOAD(r1, r0), ORI(r1, 8), STORE(r1, r0)],
    )
    start = source.index([LDI(r0, 40)], source.index([Label("length_ok")]))
    end = source.index([Label("out_gate")], start)
    source = Program(
        source[:start]
        + [
            CMPI(r5, 0x2D),
            JFAIL(Label("control_maybe_out")),
            JMP(Label("control_token_match")),
            Label("control_maybe_out"),
            CMPI(r5, 0xE1),
            JFAIL(Label("control_maybe_ack")),
            JMP(Label("control_token_match")),
            Label("control_maybe_ack"),
            CMPI(r5, 0xD2),
            JFAIL(Label("control_in_gate")),
            CMPI(r7, 145),
            JFAIL(Label("rearm")),
            LDI(r0, 171),
            LOAD(r1, r0),
            CMPI(r1, 10),
            JFAIL(Label("ack_read_data")),
            LDI(r1, 4),
            STORE(r1, r0),
            JMP(Label("rearm")),
            Label("ack_read_data"),
            CMPI(r1, 11),
            JFAIL(Label("rearm")),
            LDI(r1, 5),
            STORE(r1, r0),
            JMP(Label("rearm")),
            Label("control_in_gate"),
            CMPI(r5, 0x69),
            JFAIL(Label("out_gate")),
            LDI(r0, 171),
            LOAD(r0, r0),
            ANDI(r0, 7),
            CMPI(r0, 2),
            JFAIL(Label("maybe_read_in")),
            JMP(Label("token_match")),
            Label("maybe_read_in"),
            CMPI(r0, 3),
            JFAIL(Label("rearm")),
            JMP(Label("token_match")),
        ]
        + source[end:]
    )
    old = [Label("valid"), LDI(r0, 0), LOAD(r0, r0), JZ(r0, Label("output")), WAIT(65)]
    assert source.count(old) == 1
    source = source.replace(
        old,
        [
            Label("valid"),
            LDI(r0, 136),
            LOAD(r0, r0),
            CMPI(r0, 0x2D),
            JFAIL(Label("control_out_data")),
            LDI(r0, 152),
            LOAD(r0, r0),
            JZ(r0, Label("setup_length_low")),
            JMP(Label("form_error")),
            Label("setup_length_low"),
            LDI(r0, 151),
            LOAD(r4, r0),
            CMPLTI(r4, 9),
            JFAIL(Label("form_error")),
            JZ(r4, Label("form_error")),
            LDI(r0, 145),
            LOAD(r0, r0),
            CMPI(r0, 0x40),
            JFAIL(Label("setup_read")),
            LDI(r0, 146),
            LOAD(r0, r0),
            CMPI(r0, 1),
            JFAIL(Label("unsupported")),
            LDI(r0, 174),
            STORE(r4, r0),
            LDI(r0, 171),
            LDI(r1, 1),
            STORE(r1, r0),
            JMP(Label("control_ack")),
            Label("setup_read"),
            CMPI(r0, 0xC0),
            JFAIL(Label("unsupported")),
            LDI(r0, 146),
            LOAD(r0, r0),
            CMPI(r0, 2),
            JFAIL(Label("unsupported")),
            LDI(r0, 171),
            LOAD(r0, r0),
            CMPI(r0, 4),
            JFAIL(Label("unsupported")),
            LDI(r0, 172),
            LOAD(r0, r0),
            XOR(r0, r4),
            JZ(r0, Label("read_length_ok")),
            JMP(Label("form_error")),
            Label("read_length_ok"),
            LDI(r0, 182),
            STORE(r4, r0),
            LDI(r0, 171),
            LDI(r1, 3),
            STORE(r1, r0),
            JMP(Label("control_ack")),
            Label("control_out_data"),
            CMPI(r5, 0x4B),
            JFAIL(Label("pid_error")),
            LDI(r0, 171),
            LOAD(r0, r0),
            CMPI(r0, 1),
            JFAIL(Label("control_read_status")),
            MOV(r2, r7),
            ADDI(r2, 109),
            LDI(r0, 174),
            LOAD(r4, r0),
            XOR(r4, r2),
            JZ(r4, Label("write_length_ok")),
            JMP(Label("form_error")),
            Label("write_length_ok"),
            LDI(r0, 172),
            STORE(r2, r0),
            LDI(r1, 145),
            LDI(r3, 161),
            Label("copy_control_payload"),
            LOAD(r0, r1),
            STORE(r0, r3),
            ADDI(r1, 1),
            ADDI(r3, 1),
            DJNZ(r2, Label("copy_control_payload")),
            LDI(r0, 182),
            LDI(r1, 0),
            STORE(r1, r0),
            LDI(r0, 171),
            LDI(r1, 2),
            STORE(r1, r0),
            LDI(r0, 160),
            LDI(r1, 0x4B),
            STORE(r1, r0),
            JMP(Label("control_ack")),
            Label("control_read_status"),
            ANDI(r0, 7),
            CMPI(r0, 2),
            JFAIL(Label("not_duplicate_write")),
            JMP(Label("control_ack")),
            Label("not_duplicate_write"),
            CMPI(r0, 5),
            JFAIL(Label("unsupported")),
            CMPI(r7, 147),
            JFAIL(Label("form_error")),
            LDI(r0, 171),
            LDI(r1, 6),
            STORE(r1, r0),
            Label("control_ack"),
            WAIT(10),
        ],
    )
    # DATA PID in r5 was overwritten during CRC syndrome validation. Re-read.
    source = source.replace(
        [Label("control_out_data"), CMPI(r5, 0x4B)],
        [Label("control_out_data"), LDI(r0, 144), LOAD(r5, r0), CMPI(r5, 0x4B)],
    )
    start = source.index([Label("output")])
    end = source.index([Label("timeout")], start)
    source = Program(
        source[:start]
        + [
            Label("output"),
            LDI(r0, 171),
            LOAD(r0, r0),
            CMPI(r0, 6),
            JFAIL(Label("rearm")),
            LDI(r0, 172),
            LOAD(r2, r0),
            LDI(r0, 134),
            STORE(r2, r0),
            LDI(r1, 161),
            Label("control_result_byte"),
            LOAD(r0, r1),
            LDI(r3, 0x30),
            PWRITE(r0, r3),
            LDI(r0, 0),
            ADDI(r3, 1),
            PWRITE(r0, r3),
            ADDI(r3, 1),
            PWRITE(r0, r3),
            ADDI(r1, 1),
            DJNZ(r2, Label("control_result_byte")),
            JMP(Label("publish")),
        ]
        + source[end:]
    )
    # Address0/endpoint0 is the selected scope of this control probe. Token
    # dispatch precedes handshake dispatch to preserve minimum token/DATA gap.
    source += [
        Label("control_token_match"),
        CMPI(r7, 147),
        JFAIL(Label("ignore_token")),
        LDI(r0, 145),
        LOAD(r4, r0),
        CMPI(r4, 0),
        JFAIL(Label("ignore_token")),
        LDI(r0, 146),
        LOAD(r4, r0),
        LDI(r0, 156),
        LOAD(r6, r0),
        XOR(r4, r6),
        JZ(r4, Label("control_token_valid")),
        JMP(Label("ignore_token")),
        Label("control_token_valid"),
        LDI(r0, 157),
        STORE(r5, r0),
        JMP(Label("rearm")),
    ]
    return source.replace_comment_text(
        "GENERATED by build_usb_stream.py.", "GENERATED by build_usb_control.py."
    )


if __name__ == "__main__":
    Path(__file__).with_name("usb_control_candidate.asm").write_text(
        generate().to_asm()
    )
