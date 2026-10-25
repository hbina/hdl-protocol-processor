#!/usr/bin/env python3
"""USB bus reset and deferred SET_ADDRESS using only generic instructions."""

from pathlib import Path

from build_usb_control import generate as control_source
from tools.isa import (
    ADDI,
    ANDI,
    CMPI,
    CMPLTI,
    DJNZ,
    IN,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    OR,
    SETO,
    STORE,
    WAIT,
    XOR,
    XORI,
    r0,
    r1,
    r2,
    r3,
    r4,
    r6,
)


def token_crc_byte(address):
    crc = 31
    for bit in range(11):
        feedback = (crc ^ (address >> bit)) & 1
        crc = (crc >> 1) ^ (20 if feedback else 0)
    return (crc ^ 31) << 3


def generate():
    source = control_source()
    # Prefetch token address and replenish the idle budget in existing EOP
    # padding. The sample schedule is unchanged; token matching stays short.
    assert source.count([WAIT(25)]) == 1
    source = source.replace(
        [WAIT(25)],
        [LDI(r6, 155), LOAD(r6, r6), LDI(r1, 186), LDI(r0, 4), STORE(r0, r1), WAIT(18)],
    )
    source = source.replace([LDI(r0, 155), LOAD(r6, r0), XOR(r4, r6)], [XOR(r4, r6)])
    source = source.replace(
        [CMPI(r4, 0), JFAIL(Label("ignore_token"))],
        [
            XOR(r4, r6),
            JZ(r4, Label("address_low_ok")),
            JMP(Label("ignore_token")),
            Label("address_low_ok"),
        ],
    )
    source = source.replace(
        [Label("idle_tick")], [Label("idle_tick"), JZ(r0, Label("reset_probe"))]
    )
    source = source.replace(
        [Label("sop_tick")], [Label("sop_tick"), JZ(r0, Label("reset_probe"))]
    )
    source = source.replace(
        [DJNZ(r2, Label("wait_idle")), JMP(Label("timeout"))],
        [DJNZ(r2, Label("wait_idle")), JMP(Label("idle_expired"))],
    )
    source = source.replace(
        [DJNZ(r2, Label("wait_sop")), JMP(Label("timeout"))],
        [DJNZ(r2, Label("wait_sop")), JMP(Label("idle_expired"))],
    )
    source = source.replace(
        [Label("form_error"), LDI(r2, 17)],
        [
            Label("form_error"),
            IN(r0),
            ANDI(r0, 3),
            JZ(r0, Label("reset_probe")),
            LDI(r2, 17),
        ],
    )
    source = source.replace(
        [STORE(r1, r0), JMP(Label("rearm")), Label("rearm")],
        [
            STORE(r1, r0),
            LDI(r0, 186),
            LDI(r1, 4),
            STORE(r1, r0),
            JMP(Label("rearm")),
            Label("rearm"),
        ],
        1,
    )
    # SETUP dispatch for the standard, zero-data SET_ADDRESS request.
    marker = [CMPI(r0, 0x2D), JFAIL(Label("control_out_data"))]
    assert source.count(marker) == 1
    source = source.replace(
        marker,
        marker
        + [
            LDI(r0, 145),
            LOAD(r0, r0),
            CMPI(r0, 0),
            JFAIL(Label("vendor_setup")),
            LDI(r0, 146),
            LOAD(r0, r0),
            CMPI(r0, 5),
            JFAIL(Label("unsupported")),
            JMP(Label("setup_address")),
            Label("vendor_setup"),
        ],
    )
    source = source.replace(
        [Label("maybe_read_in"), CMPI(r0, 3), JFAIL(Label("rearm"))],
        [
            Label("maybe_read_in"),
            CMPI(r0, 7),
            JFAIL(Label("maybe_vendor_read")),
            JMP(Label("token_match")),
            Label("maybe_vendor_read"),
            CMPI(r0, 3),
            JFAIL(Label("rearm")),
        ],
    )
    source = source.replace(
        [Label("ack_read_data"), CMPI(r1, 11), JFAIL(Label("rearm"))],
        [
            Label("ack_read_data"),
            CMPI(r1, 15),
            JFAIL(Label("ack_vendor_read")),
            JMP(Label("commit_address")),
            Label("ack_vendor_read"),
            CMPI(r1, 11),
            JFAIL(Label("rearm")),
        ],
    )
    tail = [
        Label("setup_address"),
        LDI(r0, 147),
        LOAD(r4, r0),
        CMPLTI(r4, 128),
        JFAIL(Label("form_error")),
        LDI(r0, 148),
        LOAD(r1, r0),
        ADDI(r0, 1),
        LOAD(r2, r0),
        OR(r1, r2),
        ADDI(r0, 1),
        LOAD(r2, r0),
        OR(r1, r2),
        ADDI(r0, 1),
        LOAD(r2, r0),
        OR(r1, r2),
        ADDI(r0, 1),
        LOAD(r2, r0),
        OR(r1, r2),
        JZ(r1, Label("address_fields_ok")),
        JMP(Label("form_error")),
        Label("address_fields_ok"),
        LDI(r0, 175),
        STORE(r4, r0),
        LDI(r6, 16),
    ]
    for bit in range(7):
        delta = token_crc_byte(1 << bit) ^ token_crc_byte(0)
        tail += [
            MOV(r0, r4),
            ANDI(r0, (1 << bit)),
            JZ(r0, Label(f"address_bit_{bit}")),
            XORI(r6, delta),
            Label(f"address_bit_{bit}"),
        ]
    tail += [
        LDI(r0, 176),
        STORE(r6, r0),
        LDI(r0, 182),
        LDI(r1, 0),
        STORE(r1, r0),
        LDI(r0, 160),
        LDI(r1, 0x4B),
        STORE(r1, r0),
        LDI(r0, 171),
        LDI(r1, 7),
        STORE(r1, r0),
        JMP(Label("control_ack")),
        Label("commit_address"),
        LDI(r0, 175),
        LOAD(r1, r0),
        LDI(r0, 155),
        STORE(r1, r0),
        LDI(r0, 176),
        LOAD(r1, r0),
        LDI(r0, 156),
        STORE(r1, r0),
        LDI(r0, 171),
        LDI(r1, 0),
        STORE(r1, r0),
        JMP(Label("rearm")),
        Label("idle_expired"),
        LDI(r0, 186),
        LOAD(r1, r0),
        ADDI(r1, 255),
        STORE(r1, r0),
        JZ(r1, Label("timeout")),
        LDI(r2, 0),
        LDI(r3, 0),
        JMP(Label("wait_idle")),
        Label("reset_probe"),
        LDI(r4, 40),
        Label("reset_filter"),
        IN(r0),
        ANDI(r0, 3),
        JZ(r0, Label("reset_zero")),
        JMP(Label("rearm")),
        Label("reset_zero"),
        DJNZ(r4, Label("reset_filter")),
        Label("reset_confirmed"),
        SETO(56),
        LDI(r1, 0),
        LDI(r0, 155),
        STORE(r1, r0),
        LDI(r0, 157),
        STORE(r1, r0),
        LDI(r0, 171),
        STORE(r1, r0),
        ADDI(r0, 1),
        STORE(r1, r0),
        LDI(r0, 175),
        STORE(r1, r0),
        LDI(r0, 182),
        STORE(r1, r0),
        LDI(r0, 156),
        LDI(r1, 16),
        STORE(r1, r0),
        LDI(r0, 176),
        STORE(r1, r0),
        LDI(r0, 158),
        LDI(r1, 32),
        STORE(r1, r0),
        LDI(r0, 186),
        LDI(r1, 4),
        STORE(r1, r0),
        Label("reset_release"),
        IN(r0),
        ANDI(r0, 3),
        JZ(r0, Label("reset_release")),
        JMP(Label("rearm")),
    ]
    return (source + tail).replace_comment_text(
        "GENERATED by build_usb_control.py.", "GENERATED by build_usb_address.py."
    )


if __name__ == "__main__":
    Path(__file__).with_name("usb_address_candidate.asm").write_text(
        generate().to_asm()
    )
