#!/usr/bin/env python3
"""Descriptor/configuration firmware; all USB processing remains generic ISA."""

import json
from pathlib import Path

from fragments import Fragment
from build_usb_address import generate as address_source
from tools.program import Program
from tools.isa import (
    ADDI,
    CALL,
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
    PREAD,
    RET,
    SETO,
    SHR,
    STORE,
    WAIT,
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

DEVICE = bytes([18, 1, 0x10, 1, 0, 0, 0, 8, 0xAD, 0xDE, 0xEF, 0xBE, 0, 1, 0, 0, 0, 1])
CONFIG = bytes([9, 2, 18, 0, 1, 1, 0, 0x80, 50, 9, 4, 0, 0, 0, 0xFF, 0, 0, 0])


def generate(pipeline=True):
    source = address_source()
    # Remove unreachable packet-probe machinery and redundant checks.
    start, end = source.index([Label("prepare_tx")]), source.index([Label("tx_packet")])
    source = Program(source[:start] + source[end:])
    start, end = (
        source.index([Label("out_length_ok")]),
        source.index([Label("token_match")]),
    )
    source = Program(
        source[:start]
        + [Label("out_length_ok"), JMP(Label("data_gate"))]
        + source[end:]
    )
    start, end = (
        source.index([Label("token_valid")]),
        source.index([Label("ignore_token")]),
    )
    source = Program(
        source[:start] + [Label("token_valid"), JMP(Label("tx_packet"))] + source[end:]
    )
    start, end = (
        source.index([LDI(r2, 6), Label("record")]),
        source.index([LDI(r1, 130)]),
    )
    source = Program(
        source[:start]
        + [LDI(r2, 14), Label("record"), PREAD(r0, r3), DJNZ(r2, Label("record"))]
        + source[end:]
    )
    start, end = (
        source.comment_index("Parameters0..36"),
        source.index([LDI(r4, 157)]),
    )
    source = Program(
        source[:start]
        + [
            LDI(r0, 155),
            LDI(r1, 0),
            STORE(r1, r0),
            ADDI(r0, 1),
            LDI(r1, 16),
            STORE(r1, r0),
        ]
        + source[end:]
    )
    start, end = source.index([MOV(r0, r5), SHR(r0)]), source.index([MOV(r0, r7)])
    source = Program(source[:start] + source[end:])
    source = source.replace([LDI(r0, 32), STORE(r0, r4)], [LDI(r0, 128), STORE(r0, r4)])
    source = source.replace([LDI(r1, 32), STORE(r1, r0)], [LDI(r1, 128), STORE(r1, r0)])
    # Boot and reset initialize descriptor state, source pointer and configuration.
    source = source.replace(
        [JMP(Label("rearm")), Label("rearm")],
        [CALL(Label("enum_init")), JMP(Label("rearm")), Label("rearm")],
        1,
    )
    source = source.replace(
        [Label("reset_release")], [CALL(Label("enum_init")), Label("reset_release")], 1
    )
    source = source.replace(
        [LDI(r7, 160), LOAD(r1, r7)],
        [LDI(r1, 160), LOAD(r1, r1), LDI(r7, 181), LOAD(r7, r7)],
    )
    # Restore ordinary vendor buffer/PID on every accepted SETUP. This happens
    # before DATA ACK; descriptor handlers overwrite the pointer as needed.
    marker = [LDI(r0, 145), LOAD(r0, r0), CMPI(r0, 0), JFAIL(Label("vendor_setup"))]
    source = source.replace(
        marker,
        [
            LDI(r0, 181),
            LDI(r1, 160),
            STORE(r1, r0),
            LDI(r0, 190),
            LDI(r1, 0),
            STORE(r1, r0),
            LDI(r0, 160),
            LDI(r1, 0x4B),
            STORE(r1, r0),
            LDI(r0, 145),
            LOAD(r0, r0),
            CMPI(r0, 0x80),
            JFAIL(Label("maybe_standard_write")),
            JMP(Label("standard_read")),
            Label("maybe_standard_write"),
            CMPI(r0, 0),
            JFAIL(Label("vendor_setup")),
        ],
    )
    source = source.replace(
        [CMPI(r0, 5), JFAIL(Label("unsupported")), JMP(Label("setup_address"))],
        [
            CMPI(r0, 5),
            JFAIL(Label("maybe_set_config")),
            LDI(r5, 0),
            JMP(Label("setup_address")),
            Label("maybe_set_config"),
            CMPI(r0, 9),
            JFAIL(Label("unsupported")),
            LDI(r5, 1),
            JMP(Label("setup_address")),
        ],
    )
    source = source.replace(
        [Label("address_fields_ok")],
        [
            Label("address_fields_ok"),
            JZ(r5, Label("address_value")),
            JMP(Label("setup_config")),
            Label("address_value"),
        ],
        1,
    )
    # Commit configuration only when the shared standard-write status is ACKed.
    source = source.replace(
        [LDI(r0, 175), STORE(r4, r0), LDI(r6, 16)],
        [
            LDI(r0, 188),
            LOAD(r1, r0),
            ADDI(r0, 1),
            STORE(r1, r0),
            LDI(r0, 175),
            STORE(r4, r0),
            LDI(r6, 16),
        ],
    )
    source = source.replace(
        [
            LDI(r0, 182),
            LDI(r1, 0),
            STORE(r1, r0),
            LDI(r0, 160),
            LDI(r1, 0x4B),
            STORE(r1, r0),
            LDI(r0, 171),
            LDI(r1, 7),
        ],
        [
            Label("standard_write_status"),
            LDI(r0, 182),
            LDI(r1, 0),
            STORE(r1, r0),
            LDI(r0, 160),
            LDI(r1, 0x4B),
            STORE(r1, r0),
            LDI(r0, 171),
            LDI(r1, 7),
        ],
    )
    source = source.replace(
        [Label("commit_address")],
        [
            Label("commit_address"),
            LDI(r0, 189),
            LOAD(r1, r0),
            LDI(r0, 188),
            STORE(r1, r0),
        ],
        1,
    )
    # Standard-read status completes the control transfer, not the runtime job.
    source = source.replace(
        [LDI(r0, 172), LOAD(r2, r0), LDI(r0, 134)],
        [
            LDI(r0, 190),
            LOAD(r0, r0),
            JZ(r0, Label("publish_vendor")),
            LDI(r0, 171),
            LDI(r1, 0),
            STORE(r1, r0),
            JMP(Label("rearm")),
            Label("publish_vendor"),
            LDI(r0, 172),
            LOAD(r2, r0),
            LDI(r0, 134),
        ],
    )
    # First implementation: update descriptor source after ACK; a separate
    # minimum-gap regression measures this path rather than assuming it fits.
    source = source.replace(
        [Label("ack_vendor_read"), CMPI(r1, 11), JFAIL(Label("rearm")), LDI(r1, 5)],
        [
            Label("ack_vendor_read"),
            CMPI(r1, 11),
            JFAIL(Label("rearm")),
            LDI(r0, 190),
            LOAD(r0, r0),
            JZ(r0, Label("vendor_ack_done")),
            JMP(Label("descriptor_ack")),
            Label("vendor_ack_done"),
            LDI(r0, 171),
            LDI(r1, 5),
        ],
    )
    tail = [
        Label("enum_init"),
        LDI(r0, 181),
        LDI(r1, 160),
        STORE(r1, r0),
        LDI(r0, 187),
        LDI(r1, 0),
        LDI(r2, 4),
        Label("enum_clear"),
        STORE(r1, r0),
        ADDI(r0, 1),
        DJNZ(r2, Label("enum_clear")),
        RET(),
        Label("setup_config"),
        CMPLTI(r4, 2),
        JFAIL(Label("unsupported")),
        LDI(r0, 189),
        STORE(r4, r0),
        LDI(r0, 155),
        LOAD(r1, r0),
        LDI(r0, 175),
        STORE(r1, r0),
        LDI(r0, 156),
        LOAD(r1, r0),
        LDI(r0, 176),
        STORE(r1, r0),
        JMP(Label("standard_write_status")),
        Label("standard_read"),
        LDI(r0, 146),
        LOAD(r0, r0),
        CMPI(r0, 8),
        JFAIL(Label("maybe_descriptor")),
        LDI(r1, 187),
        LDI(r4, 1),
        JMP(Label("begin_standard_read")),
        Label("maybe_descriptor"),
        CMPI(r0, 6),
        JFAIL(Label("unsupported")),
        LDI(r0, 147),
        LOAD(r0, r0),
        JZ(r0, Label("descriptor_index_ok")),
        JMP(Label("unsupported")),
        Label("descriptor_index_ok"),
        LDI(r0, 148),
        LOAD(r0, r0),
        CMPI(r0, 1),
        JFAIL(Label("config_descriptor")),
        LDI(r1, 40),
        JMP(Label("descriptor_length")),
        Label("config_descriptor"),
        CMPI(r0, 2),
        JFAIL(Label("unsupported")),
        LDI(r1, 58),
        Label("descriptor_length"),
        LDI(r0, 151),
        LOAD(r4, r0),
        ADDI(r0, 1),
        LOAD(r0, r0),
        JZ(r0, Label("short_length")),
        LDI(r4, 18),
        Label("short_length"),
        CMPLTI(r4, 19),
        JFAIL(Label("cap_length")),
        JMP(Label("begin_standard_read")),
        Label("cap_length"),
        LDI(r4, 18),
        Label("begin_standard_read"),
        JZ(r4, Label("form_error")),
        LDI(r0, 181),
        STORE(r1, r0),
        CMPLTI(r4, 9),
        JFAIL(Label("first_full_packet")),
        MOV(r1, r4),
        LDI(r4, 0),
        JMP(Label("store_packet_size")),
        Label("first_full_packet"),
        LDI(r1, 8),
        ADDI(r4, 248),
        Label("store_packet_size"),
        LDI(r0, 182),
        STORE(r1, r0),
        LDI(r0, 187),
        STORE(r4, r0),
        LDI(r0, 190),
        LDI(r1, 1),
        STORE(r1, r0),
        LDI(r0, 171),
        LDI(r1, 3),
        STORE(r1, r0),
        JMP(Label("control_ack")),
        Label("descriptor_ack"),
        LDI(r0, 187),
        LOAD(r4, r0),
        JZ(r4, Label("descriptor_done")),
        LDI(r0, 181),
        LOAD(r1, r0),
        ADDI(r1, 8),
        STORE(r1, r0),
        LDI(r0, 160),
        LOAD(r1, r0),
        XORI(r1, 136),
        STORE(r1, r0),
        JMP(Label("begin_next_packet")),
        Label("descriptor_done"),
        LDI(r0, 171),
        LDI(r1, 5),
        STORE(r1, r0),
        JMP(Label("rearm")),
        Label("begin_next_packet"),
        CMPLTI(r4, 9),
        JFAIL(Label("next_full_packet")),
        MOV(r1, r4),
        LDI(r4, 0),
        JMP(Label("next_size")),
        Label("next_full_packet"),
        LDI(r1, 8),
        ADDI(r4, 248),
        Label("next_size"),
        LDI(r0, 182),
        STORE(r1, r0),
        LDI(r0, 187),
        STORE(r4, r0),
        LDI(r0, 171),
        LDI(r1, 3),
        STORE(r1, r0),
        JMP(Label("rearm")),
    ]
    result = (source + tail).replace_comment_text(
        "GENERATED by build_usb_address.py.", "GENERATED by build_usb_enum.py."
    )
    return pipeline_ack(result) if pipeline else result


def pipeline_ack(source):
    # ACK packet has no CRC. Use EOP padding to prefetch staged metadata while
    # preserving the exact sample schedule on ACK and non-ACK paths.
    prefetch = Fragment([LDI(r1, 186), LDI(r0, 4), STORE(r0, r1), CMPI(r7, 145)])
    ack = Fragment()
    for reg, address in [
        (r1, 171),
        (r2, 192),
        (r3, 193),
        (r4, 194),
        (r5, 195),
        (r6, 190),
    ]:
        ack.add([LDI(reg, address), LOAD(reg, reg)])
    prefetch.add(Fragment.choose(JFAIL, [LDI(r6, 155), LOAD(r6, r6)], ack))
    prefetch.add(Fragment.delay(26 - prefetch.cycles))
    old = [
        LDI(r6, 155),
        LOAD(r6, r6),
        LDI(r1, 186),
        LDI(r0, 4),
        STORE(r0, r1),
        WAIT(18),
    ]
    assert source.count(old) == 1
    source = source.replace(old, (prefetch.program))
    # Classify one-byte handshakes before ordinary packet dispatch; token paths
    # retain the original two-cycle length-test overhead.
    old = [CMPLTI(r7, 145), JFAIL(Label("length_ok")), JMP(Label("form_error"))]
    source = source.replace(
        old,
        [
            CMPI(r7, 145),
            JFAIL(Label("length_ok")),
            LDI(r0, 144),
            LOAD(r0, r0),
            CMPI(r0, 0xD2),
            JFAIL(Label("rearm")),
            CMPI(r1, 11),
            JFAIL(Label("other_host_ack")),
            JZ(r6, Label("read_ack_done")),
            JZ(r3, Label("read_ack_done")),
            LDI(r0, 181),
            STORE(r2, r0),
            LDI(r0, 182),
            STORE(r3, r0),
            LDI(r0, 187),
            STORE(r4, r0),
            LDI(r0, 160),
            STORE(r5, r0),
            LDI(r0, 171),
            LDI(r1, 3),
            STORE(r1, r0),
            JMP(Label("rearm")),
            Label("read_ack_done"),
            LDI(r0, 171),
            LDI(r1, 5),
            STORE(r1, r0),
            JMP(Label("rearm")),
            Label("other_host_ack"),
            CMPI(r1, 10),
            JFAIL(Label("maybe_address_ack")),
            LDI(r0, 171),
            LDI(r1, 4),
            STORE(r1, r0),
            JMP(Label("rearm")),
            Label("maybe_address_ack"),
            CMPI(r1, 15),
            JFAIL(Label("rearm")),
            JMP(Label("commit_address")),
        ],
    )
    start, end = (
        source.index([Label("control_maybe_ack")]),
        source.index([Label("control_in_gate")]),
    )
    source = Program(
        source[:start]
        + [Label("control_maybe_ack"), JMP(Label("control_in_gate"))]
        + source[end:]
    )
    start, end = (
        source.index([Label("descriptor_ack")]),
        source.index([Label("begin_next_packet")]),
    )
    source = Program(source[:start] + source[end:])
    source = source[: source.index([Label("begin_next_packet")])]
    # Precompute next-descriptor metadata during the first SYNC cell. No packet
    # state commits until ACK; retries recalculate the same metadata.
    staged = Fragment(
        [
            LDI(r0, 181),
            LOAD(r4, r0),
            ADDI(r4, 8),
            LDI(r0, 192),
            STORE(r4, r0),
            LDI(r0, 187),
            LOAD(r4, r0),
            CMPLTI(r4, 9),
        ]
    )
    staged.add(
        Fragment.choose(JFAIL, [LDI(r5, 8), ADDI(r4, 248)], [MOV(r5, r4), LDI(r4, 0)])
    )
    staged.add(
        [
            LDI(r0, 193),
            STORE(r5, r0),
            ADDI(r0, 1),
            STORE(r4, r0),
            LDI(r0, 160),
            LOAD(r4, r0),
            XORI(r4, 136),
            LDI(r0, 195),
            STORE(r4, r0),
            LDI(r0, 36),
            LDI(r4, 1),
            LDI(r5, 8),
        ]
    )
    staged.add(Fragment.delay(32 - staged.cycles))
    old = [Label("stream_sync"), WAIT(20), SETO(36), WAIT(31)]
    assert source.count(old) == 1
    return source.replace(
        old, [Label("stream_sync"), WAIT(20), SETO(36)] + (staged.program)
    )


if __name__ == "__main__":
    Path(__file__).with_name("usb_enum_candidate.asm").write_text(generate().to_asm())
    Path(__file__).with_name("usb_enum_unoptimized_candidate.asm").write_text(
        generate(False).to_asm()
    )
    Path(__file__).with_name("usb_enum_constants.json").write_text(
        json.dumps({"device": list(DEVICE), "configuration": list(CONFIG)}, indent=2)
        + "\n"
    )
