#!/usr/bin/env python3
"""CAN first-post-flag and prolonged-dominance counters in generic firmware."""

from pathlib import Path

from build_can_rx_flags_compact import generate as rx_flags_source


def generate(*, compact=True, cleanup=True):
    source = rx_flags_source()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)

    # All counted receiver errors already update REC in the shared sequencer.
    # Retained unsupported EOF/intermission diagnostics are local results, not
    # another increment path for a completed physical error flag.
    begin = source.index("JZ r6, receiver_failure\n")
    end = source.index("publish:\n", begin)
    source = source[:begin] + source[end:]
    replace(
        "LDI r2, 8\nLDI r3, 32\nWAIT 255\nWAIT 1\nJMP error_delimiter_sample",
        "LDI r4, 0\nLDI r2, 8\nLDI r3, 32\nWAIT 255\nNOP\nJMP error_delimiter_sample",
    )
    begin = source.index("error_delimiter_sample:\n")
    end = source.index("error_delimited:\n", begin)
    source = (
        source[:begin]
        + """error_delimiter_sample:
INBIT r0, 1
ANDI r0, 1
JZ r0, postflag_dominant
LDI r4, 0
DJNZ r2, postflag_recessive_more
JMP error_delimited
postflag_recessive_more:
WAIT 96
JMP error_more
postflag_dominant:
ADDI r4, 1
ANDI r4, 7
JZ r4, postflag_periodic
CMPI r3, 32
JFAIL postflag_no_bonus_early
CMPI r6, 6
JFAIL postflag_no_bonus_late
postflag_bonus:
CMPI r6, 6
JFAIL postflag_transmitter
LDI r7, 8
postflag_receiver_add:
CALL increment_rec_leaf
DJNZ r7, postflag_receiver_add
JMP postflag_counted
postflag_transmitter:
CALL increment_tec
WAIT 72
JMP postflag_counted
postflag_periodic:
WAIT 2
JMP postflag_bonus
postflag_no_bonus_early:
WAIT 92
JMP postflag_counted
postflag_no_bonus_late:
WAIT 90
JMP postflag_counted
postflag_counted:
LDI r2, 8
error_more:
DJNZ r3, error_delay
JMP recovery_timeout
error_delay:
WAIT 255
WAIT 38
JMP error_delimiter_sample
"""
        + source[end:]
    )
    # Clearing the run counter adds1 clock before the final delimiter branch.
    replace(
        "error_delimited:\nWAIT 255\nWAIT 138", "error_delimited:\nWAIT 255\nWAIT 137"
    )
    if compact:
        # Early unsupported-header exits remove dead work while the valid path
        # keeps its exact old timing. No counted error case is removed.
        replace(
            """JZ r0, rx_balance_4_yes
LDI r1, 248
LDI r0, 18
STORE r0, r1
JMP rx_balance_4_end
rx_balance_4_yes:
WAIT 4
rx_balance_4_end:""",
            """JZ r0, rx_balance_4_yes
LDI r2, 18
JMP failure
rx_balance_4_yes:
WAIT 4""",
        )
        replace(
            """JFAIL rx_balance_5_yes
WAIT 2
JMP rx_balance_5_end
rx_balance_5_yes:
LDI r1, 248
LDI r0, 18
STORE r0, r1
rx_balance_5_end:""",
            "JFAIL postflag_bad_dlc\nWAIT 3",
        )
        source += "postflag_bad_dlc:\nLDI r2, 18\nJMP failure\n"
        replace("MOV r0, r6\nLDI r4, 0\nLDI r5, 0", "MOV r0, r6\nLDI r5, 0")
        # Share the two untimed passive suspension waits with a tail-free leaf.
        for label in ["passive_retry_suspend", "passive_success_suspend"]:
            replace(
                "LDI r3, 8\n" + label + ":\nWAIT 255\nWAIT 142\nDJNZ r3, " + label,
                "CALL passive_suspend",
            )
        source += "passive_suspend:\nLDI r3, 8\npassive_suspend_bit:\nWAIT 255\nWAIT 142\nDJNZ r3, passive_suspend_bit\nRET\n"
        if cleanup:
            # The first polarity observation always consumes one of the six
            # initially remaining samples, whether it resets the run or not.
            replace(
                "flag_started:\nLDI r3, 6\nLDI r1, 1\nORI r7, 64\nWAIT 255\nWAIT 38",
                "flag_started:\nLDI r3, 6\nORI r7, 64\nWAIT 255\nWAIT 39",
            )
            # Return passive state directly in its persistent consumer register.
            replace(
                """passive_state:
LDI r1, 251
LOAD r0, r1
ANDI r0, 128
LDI r1, 250
LOAD r1, r1
ANDI r1, 128
OR r0, r1
RET""",
                """passive_state:
LDI r1, 251
LOAD r7, r1
ANDI r7, 128
LDI r1, 250
LOAD r1, r1
ANDI r1, 128
OR r7, r1
RET""",
            )
            assert source.count("CALL passive_state\nMOV r7, r0") == 2
            source = source.replace(
                "CALL passive_state\nMOV r7, r0", "CALL passive_state"
            )
            replace(
                "CALL passive_state\nJZ r0, retry_ready",
                "CALL passive_state\nJZ r7, retry_ready",
            )
            replace(
                "CALL passive_state\nJZ r0, publish",
                "CALL passive_state\nJZ r7, publish",
            )
            replace(
                "LDI r4, 0\nWAIT 63\nJMP flag_drive",
                "LDI r4, 0\nWAIT 64\nJMP flag_drive",
            )
            replace(
                "LDI r4, 0\nWAIT 29\nJMP flag_drive",
                "LDI r4, 0\nWAIT 30\nJMP flag_drive",
            )
            # Rotating an isolated0/1 right twice gives the same0/64 operand
            # as six left shifts. Both original wire-cycle budgets stay intact.
            for label, padding in [("balance_118", "\nWAIT 3"), ("balance_119", "")]:
                replace(
                    f"""JZ r1, {label}_yes
XORI r0, 64
JMP {label}_end
{label}_yes:
WAIT 1
{label}_end:"""
                    + padding,
                    "ROR r1\nROR r1\nXOR r0, r1" + padding,
                )
    return source.replace(
        "# GENERATED by build_can_rx_flags_compact.py.",
        "# GENERATED by build_can_postflag.py. Shared generic post-flag counter rules.",
    )


if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "can_postflag_unoptimized_candidate.asm").write_text(
        generate(compact=False)
    )
    (here / "can_postflag_partial_compaction_candidate.asm").write_text(
        generate(cleanup=False)
    )
    (here / "can_postflag_candidate.asm").write_text(generate())
