# Capture eight samples of input 8 (ui[0]) to RAM[0..7], then replay on
# output 8 (uo[0]). Capture/replay iterations each take seven clocks.
    LDI r1, 0
    LDI r2, 8
capture:
    INBIT r0, 8
    STORE r0, r1
    ADDI r1, 1
    WAIT 1
    DJNZ r2, capture
    LDI r1, 0
    LDI r2, 8
replay:
    LOAD r0, r1
    OUTBIT r0, 8
    WAIT 1
    ADDI r1, 1
    DJNZ r2, replay
    HALT
