#!/usr/bin/env python3
"""Combined OUT/SETUP and IN packet probe; all USB semantics are firmware."""

from pathlib import Path

from fragments import Fragment
from build_usb_out import generate as out_source
from tools.isa import (
    ADDI,
    ANDI,
    CALL,
    CMPI,
    CMPLTI,
    DJNZ,
    JFAIL,
    JMP,
    JNC,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    OR,
    ORI,
    OUT,
    PREAD,
    RET,
    ROR,
    RRC,
    SETO,
    SHL,
    SHR,
    SHRC,
    STORE,
    WAIT,
    XOR,
    XORI,
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
    source = out_source()
    old = [LDI(r2, 14), Label("record"), PREAD(r0, r3), DJNZ(r2, Label("record"))]
    assert source.count(old) == 1
    source = source.replace(
        old,
        [
            LDI(r2, 6),
            Label("record"),
            PREAD(r0, r3),
            DJNZ(r2, Label("record")),
            PREAD(r0, r3),
            LDI(r1, 182),
            STORE(r0, r1),
            LDI(r2, 7),
            Label("record_tail"),
            PREAD(r0, r3),
            DJNZ(r2, Label("record_tail")),
        ],
    )
    # Preparing TX leaves the address/CRC5 token body intact. RX uses144..154,
    # TX packet159..170, counters181..185, packed waveform192..220(max29B).
    marker = [Label("rearm"), LDI(r2, 0)]
    assert source.count(marker) == 1
    source = source.replace(
        marker,
        [
            LDI(r0, 185),
            LDI(r1, 0),
            STORE(r1, r0),
            LDI(r0, 40),
            LOAD(r0, r0),
            JZ(r0, Label("rearm")),
            JMP(Label("prepare_tx")),
            Label("rearm"),
            LDI(r2, 0),
        ],
    )
    source = source.replace(
        [CMPLTI(r7, 147), JFAIL(Label("length_ok"))],
        [CMPLTI(r7, 145), JFAIL(Label("length_ok"))],
    )
    marker = [Label("length_ok"), LDI(r0, 144), LOAD(r5, r0)]
    source = source.replace(
        marker,
        marker
        + [
            LDI(r0, 40),
            LOAD(r0, r0),
            JZ(r0, Label("out_gate")),
            CMPI(r5, 0xD2),
            JFAIL(Label("in_gate")),
            CMPI(r7, 145),
            JFAIL(Label("rearm")),
            LDI(r0, 185),
            LOAD(r0, r0),
            JZ(r0, Label("rearm")),
            LDI(r0, 0x69),
            LDI(r1, 136),
            STORE(r0, r1),
            JMP(Label("publish")),
            Label("in_gate"),
            CMPI(r5, 0x69),
            JFAIL(Label("rearm")),
            JMP(Label("token_match")),
            Label("out_gate"),
            CMPLTI(r7, 147),
            JFAIL(Label("out_length_ok")),
            JMP(Label("rearm")),
            Label("out_length_ok"),
        ],
    )
    source = source.replace(
        [Label("token_valid"), LDI(r0, 157)],
        [
            Label("token_valid"),
            CMPI(r5, 0x69),
            JFAIL(Label("out_token_valid")),
            JMP(Label("tx_packet")),
            Label("out_token_valid"),
            LDI(r0, 157),
        ],
    )
    # Entire precomputation is before reception, never on an IN response path.
    tail = Fragment(
        [
            Label("prepare_tx"),
            LDI(r0, 182),
            LOAD(r6, r0),
            CMPLTI(r6, 9),
            JFAIL(Label("form_error")),
            LDI(r0, 39),
            LOAD(r4, r0),
            CMPI(r4, 0xC3),
            JFAIL(Label("check_tx_data1")),
            JMP(Label("tx_pid_valid")),
            Label("check_tx_data1"),
            CMPI(r4, 0x4B),
            JFAIL(Label("pid_error")),
            Label("tx_pid_valid"),
            LDI(r0, 160),
            STORE(r4, r0),
            LDI(r7, 161),
            LDI(r2, 255),
            LDI(r3, 255),
            JZ(r6, Label("tx_crc_done")),
            Label("tx_payload"),
            LDI(r0, 0x11),
            PREAD(r4, r0),
            STORE(r4, r7),
            ADDI(r7, 1),
            XOR(r2, r4),
            LDI(r5, 8),
            Label("tx_crc_bit"),
            SHRC(r3),
            RRC(r2),
            JNC(Label("tx_crc_no_xor")),
            XORI(r2, 1),
            XORI(r3, 160),
            Label("tx_crc_no_xor"),
            DJNZ(r5, Label("tx_crc_bit")),
            DJNZ(r6, Label("tx_payload")),
            Label("tx_crc_done"),
            XORI(r2, 255),
            XORI(r3, 255),
            STORE(r2, r7),
            ADDI(r7, 1),
            STORE(r3, r7),
            LDI(r0, 159),
            LDI(r1, 128),
            STORE(r1, r0),
            LDI(r0, 183),
            LDI(r1, 159),
            STORE(r1, r0),
            LDI(r0, 182),
            LOAD(r1, r0),
            ADDI(r1, 4),
            LDI(r0, 184),
            STORE(r1, r0),
            LDI(r7, 192),
            LDI(r6, 0),
            LDI(r5, 4),
            LDI(r4, 2),
            LDI(r3, 0),
            Label("encode_byte"),
            LDI(r0, 183),
            LOAD(r1, r0),
            LOAD(r1, r1),
            LDI(r2, 8),
            Label("encode_bit"),
            SHRC(r1),
            JNC(Label("encode_zero")),
            ADDI(r3, 1),
            JMP(Label("encode_line")),
            Label("encode_zero"),
            XORI(r4, 3),
            LDI(r3, 0),
            Label("encode_line"),
            CALL(Label("pack_line")),
            CMPI(r3, 6),
            JFAIL(Label("no_tx_stuff")),
            XORI(r4, 3),
            LDI(r3, 0),
            CALL(Label("pack_line")),
            Label("no_tx_stuff"),
            DJNZ(r2, Label("encode_bit")),
            LDI(r0, 183),
            LOAD(r1, r0),
            ADDI(r1, 1),
            STORE(r1, r0),
            LDI(r0, 184),
            LOAD(r1, r0),
            ADDI(r1, 255),
            STORE(r1, r0),
            JZ(r1, Label("encode_eop")),
            JMP(Label("encode_byte")),
            Label("encode_eop"),
            LDI(r4, 0),
            CALL(Label("pack_line")),
            CALL(Label("pack_line")),
            LDI(r4, 2),
            CALL(Label("pack_line")),
            MOV(r0, r7),
            ADDI(r0, 64),
            SHL(r0),
            SHL(r0),
            MOV(r1, r5),
            XORI(r1, 255),
            ADDI(r1, 5),
            OR(r0, r1),
            LDI(r1, 181),
            STORE(r0, r1),
            CMPI(r5, 4),
            JFAIL(Label("pack_partial")),
            JMP(Label("rearm")),
            Label("pack_partial"),
            SHR(r6),
            SHR(r6),
            DJNZ(r5, Label("pack_partial")),
            STORE(r6, r7),
            JMP(Label("rearm")),
            Label("pack_line"),
            SHR(r6),
            SHR(r6),
            MOV(r0, r4),
            ROR(r0),
            ROR(r0),
            OR(r6, r0),
            DJNZ(r5, Label("packed")),
            STORE(r6, r7),
            ADDI(r7, 1),
            LDI(r5, 4),
            Label("packed"),
            RET(),
            Label("tx_packet"),
            LDI(r0, 185),
            LDI(r1, 1),
            STORE(r1, r0),
            LDI(r0, 181),
            LOAD(r6, r0),
            LDI(r1, 192),
            LOAD(r2, r1),
            LDI(r3, 4),
            MOV(r0, r2),
            ANDI(r0, 3),
            SHL(r0),
            SHL(r0),
            ORI(r0, 32),
            WAIT(20),
            JMP(Label("tx_cell_0")),
        ]
    )
    for phase, period in enumerate([33, 33, 34]):
        tail.add(
            [
                Label(f"tx_cell_{phase}"),
                OUT(r0),
                DJNZ(r6, Label(f"tx_more_{phase}")),
                JMP(Label(f"tx_finish_{phase}")),
                Label(f"tx_more_{phase}"),
                SHR(r2),
                SHR(r2),
            ]
        )
        tail.add(
            Fragment.choose(
                lambda t: DJNZ(r3, t), (), [ADDI(r1, 1), LOAD(r2, r1), LDI(r3, 4)]
            )
        )
        tail.add([MOV(r0, r2), ANDI(r0, 3), SHL(r0), SHL(r0), ORI(r0, 32)])
        tail.add(Fragment.delay(period - 16)).add(
            [JMP(Label(f"tx_cell_{(phase + 1) % 3}"))]
        )
        tail.add([Label(f"tx_finish_{phase}")]).add(Fragment.delay(period - 3))
        tail.add([SETO(56), JMP(Label("rearm"))])
    source += tail.program
    source = source.replace_comment_text(
        "GENERATED by build_usb_out.py.", "GENERATED by build_usb_in.py."
    )
    return source


if __name__ == "__main__":
    Path(__file__).with_name("usb_in_candidate.asm").write_text(generate().to_asm())
