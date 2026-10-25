#!/usr/bin/env python3
"""CAN winner reception/retransmission using the existing generic ISA only."""

from pathlib import Path

from build_can_recovery import generate as recovery_source
from fragments import Fragment, load, put
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
    NOP,
    OR,
    PREAD,
    ROL,
    SHL,
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
from tools.program import Comment


def generate():
    source = recovery_source()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)

    replace(
        [Label("legacy_dispatch"), CMPI(r0, 2)],
        [
            Label("legacy_dispatch"),
            CMPI(r0, 4),
            JFAIL(Label("ordinary_dispatch")),
            LDI(r6, 2),
            JMP(Label("tx_entry")),
            Label("ordinary_dispatch"),
            CMPI(r0, 2),
        ],
    )
    replace([Label("tx_entry")], [Label("tx_entry"), LDI(r7, 136)])
    replace(
        [Label("tx_payload_byte"), LDI(r3, 0x11), PREAD(r0, r3)],
        [
            Label("tx_payload_byte"),
            CMPI(r6, 4),
            JFAIL(Label("payload_from_fifo")),
            LOAD(r0, r7),
            JMP(Label("payload_ready")),
            Label("payload_from_fifo"),
            LDI(r3, 0x11),
            PREAD(r0, r3),
            STORE(r0, r7),
            Label("payload_ready"),
            ADDI(r7, 1),
        ],
    )
    replace(
        [ADDI(r5, 1), LDI(r1, 242)],
        [
            ADDI(r5, 1),
            CMPI(r6, 4),
            JFAIL(Label("tx_mode_ready")),
            LDI(r6, 2),
            Label("tx_mode_ready"),
            LDI(r4, 0),
            LDI(r7, 0),
            LDI(r1, 242),
        ],
    )
    # Preserve the previous dominant run before the balanced fetch updates it.
    cache = load(242)
    cache.add(Fragment.choose(lambda t: JZ(r0, t), load(243), [LDI(r0, 0)]))
    cache.add([LDI(r1, 248), STORE(r0, r1)])
    replace([Label("tx_tx_cell")], [Label("tx_tx_cell")] + cache.program)
    replace(
        [Label("tx_sample_ok"), WAIT(44)],
        [Label("tx_sample_ok")] + (Fragment.delay(45 - cache.cycles).program),
    )

    # Mirror the logical TX prefix CRC in generic registers. Stuff bits do not
    # enter CRC. If arbitration flips the current1 to0, XOR polynomial0x4599
    # repairs precisely that step; earlier logical bits were common to both.
    crc = Fragment(
        [
            MOV(r1, r7),
            ANDI(r1, 64),
            MOV(r2, r0),
            SHL(r2),
            SHL(r2),
            SHL(r2),
            SHL(r2),
            SHL(r2),
            SHL(r2),
            XOR(r1, r2),
            SHL(r7),
            ANDI(r7, 127),
            ROL(r4),
            MOV(r2, r4),
            ANDI(r2, 1),
            OR(r7, r2),
            ANDI(r4, 254),
        ]
    )
    crc.add(Fragment.choose(lambda t: JZ(r1, t), (), [XORI(r4, 0x99), XORI(r7, 0x45)]))
    mirror = load(244, r1).add(Fragment.choose(lambda t: JZ(r1, t), crc))
    replace(
        [Label("tx_normal_cell"), WAIT(255), WAIT(38)],
        [Label("tx_normal_cell")]
        + (mirror.program + Fragment.delay(295 - mirror.cycles).program),
    )
    replace(
        [LDI(r2, 22), JMP(Label("failure"))],
        [
            CMPI(r6, 2),
            JFAIL(Label("legacy_arbitration_loss")),
            JMP(Label("winner_loss")),
            Label("legacy_arbitration_loss"),
            LDI(r2, 22),
            JMP(Label("failure")),
        ],
    )
    # At winner_loss entry,19 clocks have elapsed since the TX sample.
    loss = Fragment(
        [
            Label("winner_loss"),
            LDI(r6, 3),
            XORI(r4, 0x99),
            XORI(r7, 0x45),
            LDI(r1, 247),
            LOAD(r1, r1),
            MOV(r0, r1),
            ADDI(r1, 255),
            LDI(r2, 0),
            STORE(r2, r1),
            Comment("Remaining header bits =163-next logical pointer, modulo256."),
            XORI(r0, 255),
            ADDI(r0, 164),
            LDI(r1, 244),
            STORE(r0, r1),
        ]
    )
    loss.add(put(242, 0))
    loss.add(load(248)).add([ADDI(r0, 1), LDI(r1, 243), STORE(r0, r1)])
    loss.add(put(245, 0)).add(put(248, 0))
    loss.add([MOV(r2, r4), MOV(r3, r7)])
    loss.add(Fragment.delay(400 - 19 - loss.cycles - 1)).add([JMP(Label("rx_sample"))])
    source += loss.program

    replace(
        [
            Label("rx_output_done"),
            LDI(r1, 249),
            LOAD(r0, r1),
            ADDI(r0, 3),
            LDI(r1, 134),
            STORE(r0, r1),
            JMP(Label("publish")),
        ],
        [
            Label("rx_output_done"),
            LDI(r1, 249),
            LOAD(r0, r1),
            ADDI(r0, 3),
            MOV(r2, r0),
            LDI(r1, 134),
            LOAD(r0, r1),
            Label("accumulate_output"),
            ADDI(r0, 1),
            DJNZ(r2, Label("accumulate_output")),
            STORE(r0, r1),
            CMPI(r6, 3),
            JFAIL(Label("publish")),
            CMPLTI(r5, 3),
            JFAIL(Label("winner_attempts_exhausted")),
            LDI(r6, 4),
            JMP(Label("tx_entry")),
            Label("winner_attempts_exhausted"),
            LDI(r2, 22),
            JMP(Label("failure")),
        ],
    )
    replace(
        [
            Label("publish"),
            JZ(r6, Label("ordinary_event")),
            LDI(r1, 136),
            STORE(r5, r1),
            Label("ordinary_event"),
        ],
        [
            Label("publish"),
            LDI(r1, 136),
            LDI(r0, 0),
            JZ(r6, Label("detail_ready")),
            MOV(r0, r5),
            Label("detail_ready"),
            STORE(r0, r1),
            LDI(r1, 137),
            LDI(r2, 7),
            LDI(r0, 0),
            Label("clear_saved_payload"),
            STORE(r0, r1),
            ADDI(r1, 1),
            DJNZ(r2, Label("clear_saved_payload")),
        ],
    )
    # r4 is now CRC low. Use the already-existing attempt counter for the cap.
    replace(
        [Label("ack_error"), JZ(r6, Label("legacy_no_ack")), ADDI(r4, 255)],
        [Label("ack_error"), JZ(r6, Label("legacy_no_ack")), NOP()],
    )
    replace(
        [JZ(r4, Label("retry_exhausted"))],
        [CMPLTI(r5, 3), JFAIL(Label("retry_exhausted"))],
    )
    replace(
        [ADDI(r5, 1), WAIT(27), JMP(Label("tx_tx_cell"))],
        [LDI(r4, 0), LDI(r7, 0), ADDI(r5, 1)]
        + (Fragment.delay(28 - 1 - 2 - cache.cycles).program)
        + [JMP(Label("tx_tx_cell"))],
    )
    replace([Label("retry_exhausted"), WAIT(95)], [Label("retry_exhausted"), WAIT(94)])
    return source.replace_comment_text(
        "GENERATED by build_can_recovery.py.",
        "GENERATED by build_can_winner.py. Operation4=TX/winner RX/retry.",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_winner_candidate.asm").write_text(generate().to_asm())
