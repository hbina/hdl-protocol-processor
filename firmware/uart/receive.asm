    LDI r0, 0                #   0: 1000
    OUT r0, 0                #   1: 4400
    OUT r0, 1                #   2: 4401
    LDI r1, 252              #   3: 11fc
    OE r1, 0                 #   4: 4900
    LDI r2, 241              #   5: 12f1
    STORE r0, r2             #   6: 3402
    ADDI r2, 1               #   7: c201
    STORE r0, r2             #   8: 3402
    ADDI r2, 1               #   9: c201
    STORE r0, r2             #  10: 3402
    ADDI r2, 1               #  11: c201
    LDI r3, 0                #  12: 1300
arm:
    WAITPIN 1, 1             #  13: f501
    LDI r2, 18               #  14: 1212
idle_0:
    INBIT r1, 1              #  15: e501
    JZ r1, 13                #  16: 910d
    DJNZ r2, 15              #  17: a20f
    LDI r1, 1                #  18: 1101
ready:
    OUTBIT r1, 2             #  19: e102
start:
    WAITPIN 1, 0             #  20: f401
    LDI r1, 0                #  21: 1100
    OUTBIT r1, 2             #  22: e102
    OUTBIT r1, 3             #  23: e103
    WAIT 20                  #  24: 7014
    INBIT r1, 1              #  25: e501
    JZ r1, 28                #  26: 911c
    JMP 49                   #  27: 8031
start_valid:
    LDI r0, 0                #  28: 1000
    LDI r2, 8                #  29: 1208
    WAIT 45                  #  30: 702d
data:
    INBIT r1, 1              #  31: e501
    SHR r0                   #  32: d400
    ROR r1                   #  33: dd00
    OR r0, r1                #  34: b801
    WAIT 44                  #  35: 702c
    DJNZ r2, 31              #  36: a21f
    INBIT r1, 1              #  37: e501
    JZ r1, 56                #  38: 9138
    CMPLTI r3, 128           #  39: 1f80
    JFAIL 63                 #  40: 883f
    STORE r0, r3             #  41: 3403
    ADDI r3, 1               #  42: c301
    OUT r0, 1                #  43: 4401
    OUTBIT r1, 3             #  44: e103
    CMPI r3, 128             #  45: 1780
    JFAIL 19                 #  46: 8813
    OUTBIT r1, 7             #  47: e107
    JMP 19                   #  48: 8013
false_start:
    LDI r1, 1                #  49: 1101
    OUTBIT r1, 4             #  50: e104
    LDI r2, 241              #  51: 12f1
    LOAD r1, r2              #  52: 2502
    ADDI r1, 1               #  53: c101
    STORE r1, r2             #  54: 3502
    JMP 13                   #  55: 800d
framing_error:
    LDI r1, 1                #  56: 1101
    OUTBIT r1, 5             #  57: e105
    LDI r2, 242              #  58: 12f2
    LOAD r1, r2              #  59: 2502
    ADDI r1, 1               #  60: c101
    STORE r1, r2             #  61: 3502
    JMP 13                   #  62: 800d
overflow:
    OUTBIT r1, 6             #  63: e106
    LDI r2, 243              #  64: 12f3
    LOAD r1, r2              #  65: 2502
    ADDI r1, 1               #  66: c101
    STORE r1, r2             #  67: 3502
    LDI r1, 1                #  68: 1101
    JMP 19                   #  69: 8013
