    LDI r1, 0                #   0: 1100
    LDI r0, 0                #   1: 1000
    STORE r0, r1             #   2: 3401
    ADDI r1, 1               #   3: c101
    LDI r0, 165              #   4: 10a5
    STORE r0, r1             #   5: 3401
    ADDI r1, 1               #   6: c101
    LDI r0, 255              #   7: 10ff
    STORE r0, r1             #   8: 3401
    ADDI r1, 1               #   9: c101
    LDI r0, 85               #  10: 1055
    STORE r0, r1             #  11: 3401
    ADDI r1, 1               #  12: c101
    LDI r3, 1                #  13: 1301
    OUTBIT r3, 0             #  14: e300
    OEBIT r3, 0              #  15: eb00
    LDI r1, 0                #  16: 1100
    WAIT 49                  #  17: 7031
frame:
    LDI r0, 0                #  18: 1000
    OUTBIT r0, 0             #  19: e000
    LOAD r0, r1              #  20: 2401
    LDI r2, 8                #  21: 1208
    LDI r3, 1                #  22: 1301
    WAIT 44                  #  23: 702c
data:
    OUTBIT r0, 0             #  24: e000
    SHR r0                   #  25: d400
    WAIT 46                  #  26: 702e
    DJNZ r2, 24              #  27: a218
    OUTBIT r3, 0             #  28: e300
    ADDI r1, 1               #  29: c101
    CMPI r1, 4               #  30: 1504
    JFAIL 34                 #  31: 8822
    LDI r1, 0                #  32: 1100
    JMP 36                   #  33: 8024
no_wrap:
    NOP                      #  34: 0000
    NOP                      #  35: 0000
next_frame:
    WAIT 41                  #  36: 7029
    JMP 18                   #  37: 8012
