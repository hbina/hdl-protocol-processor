#!/usr/bin/env python3
"""Further generic firmware reuse for the frozen bounded CAN tail draft."""

from pathlib import Path

from build_can_tail import generate as prior_source


def generate(*, safe_idle=True):
    source = prior_source()

    def replace(old, new, count=1):
        nonlocal source
        assert source.count(old) == count, (old, source.count(old))
        source = source.replace(old, new)

    feedback = "MOV r0, r3\nANDI r0, 64\nLDI r1, 246\nLOAD r1, r1\nROR r1\nROR r1\nXOR r0, r1\n"
    shift = "SHL r3\nANDI r3, 127\nROL r2\nMOV r1, r2\nANDI r1, 1\nOR r3, r1\nANDI r2, 254\n"
    rx = (
        feedback
        + "WAIT 3\n"
        + shift
        + "JZ r0, rx_balance_3_yes\nXORI r2, 0x99\nXORI r3, 0x45\nJMP rx_balance_3_end\nrx_balance_3_yes:\nWAIT 2\nrx_balance_3_end:\n"
    )
    replace(rx, "CALL crc_step\nWAIT 1\n")
    offline = (
        feedback.replace("LDI r1, 246\n", "")
        + shift
        + "JZ r0, tx_balance_101_yes\nXORI r2, 0x99\nXORI r3, 0x45\ntx_balance_101_yes:\ntx_balance_101_end:\n"
    )
    replace(offline, "CALL crc_step\n")
    begin = source.index("MOV r1, r7\nANDI r1, 64\n")
    end = source.index("balance_107_end:\n", begin)
    source = (
        source[:begin]
        + """MOV r2, r4
MOV r3, r7
CALL crc_step
MOV r4, r2
MOV r7, r3
LDI r1, 246
LOAD r0, r1
"""
        + source[end:]
    )
    replace("WAIT 19\nJMP balance_107_end", "WAIT 26\nJMP balance_107_end")
    replace("balance_107_end:\nWAIT 255\nWAIT 13", "balance_107_end:\nWAIT 255\nWAIT 6")
    source += (
        "crc_step:\n"
        + feedback
        + shift
        + """JZ r0, crc_zero_feedback
XORI r2, 0x99
XORI r3, 0x45
JMP crc_step_done
crc_zero_feedback:
WAIT 2
crc_step_done:
RET
"""
    )
    # Output encoding and offline staging do not have pin deadlines.
    replace("MOV r2, r0\nCALL emit_byte\nMOV r4, r2", "MOV r4, r0\nCALL emit_byte")
    replace(
        "MOV r0, r2\nLDI r2, 254\nSTORE r0, r2\nMOV r0, r3",
        "LDI r0, 254\nSTORE r2, r0\nMOV r0, r3",
    )
    old = "LDI r0, 0\n" + "".join(
        f"LDI r1, {address}\nLOAD r1, r1\nSHL r0\nOR r0, r1\n"
        for address in range(159, 163)
    )
    new = (
        "LDI r1, 159\nLOAD r0, r1\n"
        + "SHL r0\nADDI r1, 1\nLOAD r4, r1\nOR r0, r4\n" * 3
    )
    replace(old, new)
    replace("JFAIL postflag_bad_dlc\nWAIT 3", "JFAIL postflag_bad_dlc\nWAIT 6")
    # Shared saturating store tails preserve both existing leaf cycle counts.
    replace(
        "increment_rec_leaf:\nLDI r1, 250\nLOAD r0, r1\nCMPI r0, 255\nJFAIL balance_116_yes\nWAIT 1\nJMP balance_116_end\nbalance_116_yes:\nADDI r0, 1\nSTORE r0, r1\nbalance_116_end:\nRET",
        "increment_rec_leaf:\nLDI r1, 250\nLOAD r0, r1\nCMPI r0, 255\nJFAIL balance_116_yes\nJMP rec_store\nbalance_116_yes:\nADDI r0, 1\nrec_store:\nSTORE r0, r1\nRET",
    )
    replace("JMP flagbit_rec_store", "JMP rec_store")
    replace(
        "flagbit_rec_saturates:\nLDI r0, 255\nNOP\nflagbit_rec_store:\nSTORE r0, r1\nRET",
        "flagbit_rec_saturates:\nLDI r0, 255\nJMP rec_store",
    )
    # Reorder the leaf feedback so offline TX can pass its already-loaded bit.
    replace(
        "crc_step:\n" + feedback,
        "crc_step:\nLDI r1, 246\nLOAD r1, r1\ncrc_from_r1:\nROR r1\nROR r1\nMOV r0, r3\nANDI r0, 64\nXOR r0, r1\n",
    )
    replace(
        "LOAD r0, r1\nLDI r1, 246\nSTORE r0, r1\nCALL crc_step",
        "LOAD r0, r1\nMOV r1, r0\nCALL crc_from_r1",
    )
    # Ignore the last EOF polarity without a dead input read. Overload uses
    # twelve generic delay segments; the public dominant pulse remains2400
    # clocks, and the existing lack of per-bit overload fault checks is kept.
    replace(
        "LDI r7, 3\nINBIT r0, 1\nWAIT 255\nWAIT 140", "LDI r7, 3\nWAIT 255\nWAIT 141"
    )
    replace(
        "rx_overload_allowed:\nLDI r3, 6\nWAIT 191",
        "rx_overload_allowed:\nLDI r3, 12\nWAIT 192",
    )
    replace(
        "rx_overload_bit:\nWAIT 255\nWAIT 141\nDJNZ r3, rx_overload_bit\nWAIT 4",
        "rx_overload_bit:\nWAIT 197\nDJNZ r3, rx_overload_bit\nWAIT 10",
    )
    # INBIT replaces only bit0. These paths already keep r0 upper bits zero;
    # frame-state initialization below supplies that invariant for TX idle.
    # Compensate the timed paths using existing padding words.
    replace(
        "shared_idle_bus:\nINBIT r0, 1\nANDI r0, 1\nJZ r0, shared_busy_bus\nWAIT 255\nWAIT 139",
        "shared_idle_bus:\nINBIT r0, 1\nJZ r0, shared_busy_bus\nWAIT 255\nWAIT 140",
    )
    replace("rx_sof_wait:\nINBIT r0, 1\nANDI r0, 1", "rx_sof_wait:\nINBIT r0, 1")
    replace(
        "rx_sof_seen:\nLDI r2, 0\nLDI r3, 0\nWAIT 192",
        "rx_sof_seen:\nLDI r2, 0\nLDI r3, 0\nWAIT 193",
    )
    replace(
        "INBIT r0, 1\nANDI r0, 1\nWAIT 147\nJMP rx_fault_prepare",
        "INBIT r0, 1\nWAIT 148\nJMP rx_fault_prepare",
    )
    replace(
        "INBIT r0, 1\nANDI r0, 1\nJZ r0, rx_ack_ok\nLDI r2, 20\nWAIT 145",
        "INBIT r0, 1\nJZ r0, rx_ack_ok\nLDI r2, 20\nWAIT 146",
    )
    replace("rx_ack_ok:\nWAIT 196", "rx_ack_ok:\nWAIT 197")
    replace(
        "rx_tail:\nINBIT r0, 1\nANDI r0, 1\nJZ r0, rx_form_error\nWAIT 255\nWAIT 139",
        "rx_tail:\nINBIT r0, 1\nJZ r0, rx_form_error\nWAIT 255\nWAIT 140",
    )
    replace(
        "rx_form_error:\nLDI r2, 17\nWAIT 145", "rx_form_error:\nLDI r2, 17\nWAIT 146"
    )
    replace(
        "rx_intermission:\nINBIT r0, 1\nANDI r0, 1\nJZ r0, rx_intermission_dominant\nWAIT 255\nWAIT 139",
        "rx_intermission:\nINBIT r0, 1\nJZ r0, rx_intermission_dominant\nWAIT 255\nWAIT 140",
    )
    replace(
        "rx_overload_delimiter:\nINBIT r0, 1\nANDI r0, 1",
        "rx_overload_delimiter:\nINBIT r0, 1",
    )
    replace(
        "LDI r2, 3\nWAIT 255\nWAIT 137\nJMP rx_intermission",
        "LDI r2, 3\nWAIT 255\nWAIT 138\nJMP rx_intermission",
    )
    replace(
        "rx_overload_delay:\nWAIT 255\nWAIT 135",
        "rx_overload_delay:\nWAIT 255\nWAIT 136",
    )
    if safe_idle:
        # The generic input-bit operation preserves bits7:1. Return r0=1
        # rather than144 from setup so dominant idle samples compare as zero.
        # All addresses/values and total instruction/cycle counts are unchanged.
        replace(
            "reset_frame_state:\nLDI r1, 242\nLDI r0, 1\nSTORE r0, r1\nLDI r1, 243\nLDI r0, 0\nSTORE r0, r1\nLDI r1, 245\nSTORE r0, r1\nLDI r1, 247\nLDI r0, 144\nSTORE r0, r1\nRET",
            "reset_frame_state:\nLDI r1, 247\nLDI r0, 144\nSTORE r0, r1\nLDI r1, 243\nLDI r0, 0\nSTORE r0, r1\nLDI r1, 245\nSTORE r0, r1\nLDI r1, 242\nLDI r0, 1\nSTORE r0, r1\nRET",
        )
    return source.replace(
        "# GENERATED by build_can_tail.py. UNVERIFIED capacity integration;",
        "# GENERATED by build_can_tail_compact.py. Shared generic firmware routines;",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_tail_compact_candidate.asm").write_text(generate())
    Path(__file__).with_name("can_tail_compact_unsafe_candidate.asm").write_text(
        generate(safe_idle=False)
    )
