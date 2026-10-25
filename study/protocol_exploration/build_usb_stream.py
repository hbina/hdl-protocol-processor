#!/usr/bin/env python3
"""Live generic-instruction USB TX; no payload CRC/waveform precomputation."""

from pathlib import Path

from fragments import Fragment
from build_usb_in import generate as packet_source
from tools.isa import JNC
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
    NOP,
    OUT,
    PREAD,
    RET,
    RRC,
    SETO,
    SHRC,
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


def crc_seed(pid):
    # Reverse eight CRC steps so including PID leaves the normal0xffff seed
    # at the first payload bit. These are PID constants, not payload FCS.
    value = 0xFFFF
    for bit in range(7, -1, -1):
        old_low = value >> 15
        value = (((value ^ (0xA001 if old_low else 0)) << 1) | old_low) & 0xFFFF
        value ^= (pid >> bit) & 1
    return value


def generate():
    source = packet_source().split([Label("prepare_tx")], 1)[0]
    out = Fragment(source)
    out.add(
        [
            Label("prepare_tx"),
            LDI(r0, 182),
            LOAD(r6, r0),
            CMPLTI(r6, 9),
            JFAIL(Label("form_error")),
            LDI(r0, 39),
            LOAD(r4, r0),
            CMPI(r4, 0xC3),
            JFAIL(Label("stream_data1")),
            JMP(Label("stream_pid_ok")),
            Label("stream_data1"),
            CMPI(r4, 0x4B),
            JFAIL(Label("pid_error")),
            Label("stream_pid_ok"),
            LDI(r7, 160),
            STORE(r4, r7),
            JZ(r6, Label("rearm")),
            Label("stream_payload"),
            LDI(r0, 0x11),
            PREAD(r4, r0),
            ADDI(r7, 1),
            STORE(r4, r7),
            DJNZ(r6, Label("stream_payload")),
            JMP(Label("rearm")),
            Label("tx_packet"),
            LDI(r0, 185),
            LDI(r1, 1),
            STORE(r1, r0),
            LDI(r0, 182),
            LOAD(r6, r0),
            ADDI(r6, 3),
            LDI(r7, 160),
            LOAD(r1, r7),
            LDI(r5, 8),
            LDI(r4, 1),
            LDI(r0, 36),
            CMPI(r1, 0xC3),
            JFAIL(Label("stream_seed1")),
        ]
    )
    seed0, seed1 = crc_seed(0xC3), crc_seed(0x4B)
    out.add(
        [
            LDI(r2, (seed0 & 255)),
            LDI(r3, (seed0 >> 8)),
            JMP(Label("stream_sync")),
            Label("stream_seed1"),
            LDI(r2, (seed1 & 255)),
            LDI(r3, (seed1 >> 8)),
            Label("stream_sync"),
            WAIT(20),
        ]
    )
    # SYNC has seven zero bits and one one. It ends K, with one trailing1.
    for index, line in enumerate([36, 40, 36, 40, 36, 40, 36, 36]):
        out.add([SETO(line)])
        period = [33, 33, 34][index % 3]
        if index < 7:
            out.add(Fragment.delay(period - 1))
        else:
            out.add([CALL(Label("stream_bit"))]).add(Fragment.delay(period - 17)).add(
                [JMP(Label("stream_cell_2"))]
            )
    for phase, period in enumerate([33, 33, 34]):
        following = (phase + 1) % 3
        out.add(
            [
                Label(f"stream_cell_{phase}"),
                OUT(r0),
                CMPI(r4, 6),
                JFAIL(Label(f"stream_advance_{phase}")),
                XORI(r0, 12),
                LDI(r4, 0),
            ]
        )
        out.add(Fragment.delay(period - 6)).add(
            [JMP(Label(f"stream_stuff_{following}"))]
        )
        out.add(
            [
                Label(f"stream_stuff_{phase}"),
                OUT(r0),
                NOP(),
                JMP(Label(f"stream_advance_{phase}")),
            ]
        )
        out.add(
            [
                Label(f"stream_advance_{phase}"),
                DJNZ(r5, Label(f"stream_same_{phase}")),
                DJNZ(r6, Label(f"stream_new_{phase}")),
            ]
        )
        # Last logical bit (and any mandatory final stuff) precedes EOP.
        out.add(Fragment.delay(period - 5)).add([SETO(32)])
        out.add(Fragment.delay([33, 33, 34][following] - 1)).add([SETO(32)])
        out.add(Fragment.delay([33, 33, 34][(phase + 2) % 3] - 1)).add([SETO(40)])
        out.add(Fragment.delay(period - 1)).add([SETO(56), JMP(Label("rearm"))])
        out.add(
            [
                Label(f"stream_new_{phase}"),
                ADDI(r7, 1),
                LDI(r5, 8),
                CMPI(r6, 2),
                JFAIL(Label(f"stream_maybe_high_{phase}")),
                MOV(r1, r2),
                XORI(r1, 255),
                CALL(Label("stream_bit")),
            ]
        )
        out.add(Fragment.delay(period - 27)).add(
            [JMP(Label(f"stream_cell_{following}"))]
        )
        out.add(
            [
                Label(f"stream_maybe_high_{phase}"),
                CMPI(r6, 1),
                JFAIL(Label(f"stream_load_{phase}")),
                MOV(r1, r3),
                XORI(r1, 255),
                CALL(Label("stream_bit")),
            ]
        )
        out.add(Fragment.delay(period - 29)).add(
            [JMP(Label(f"stream_cell_{following}"))]
        )
        out.add(
            [Label(f"stream_load_{phase}"), LOAD(r1, r7), CALL(Label("stream_bit"))]
        )
        out.add(Fragment.delay(period - 29)).add(
            [JMP(Label(f"stream_cell_{following}"))]
        )
        out.add([Label(f"stream_same_{phase}"), CALL(Label("stream_bit"))])
        out.add(Fragment.delay(period - 20)).add(
            [JMP(Label(f"stream_cell_{following}"))]
        )
    out.add([Label("stream_bit"), SHRC(r1)])
    out.add(
        Fragment.choose(JNC, [XORI(r0, 12), LDI(r4, 0)], [ADDI(r4, 1), XORI(r2, 1)])
    )
    crc = Fragment([SHRC(r3), RRC(r2)]).add(
        Fragment.choose(JNC, (), [XORI(r2, 1), XORI(r3, 160)])
    )
    out.add([CMPLTI(r6, 3)]).add(Fragment.choose(JFAIL, crc, ())).add([RET()])
    result = out.program
    return result.replace_comment_text(
        "GENERATED by build_usb_in.py.", "GENERATED by build_usb_stream.py."
    )


if __name__ == "__main__":
    Path(__file__).with_name("usb_stream_candidate.asm").write_text(generate().to_asm())
