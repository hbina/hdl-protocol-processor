    LDI r0, 1                #   0: 1001
    OUT r0, 0                #   1: 4400
    LDI r1, 61               #   2: 113d
    OE r1, 0                 #   3: 4900
    LDI r0, 0                #   4: 1000
    OUT r0, 1                #   5: 4401
    LDI r2, 0                #   6: 1200
    STORE r0, r2             #   7: 3402
    LDI r2, 241              #   8: 12f1
    STORE r0, r2             #   9: 3402
    ADDI r2, 1               #  10: c201
    STORE r0, r2             #  11: 3402
arm:
    WAITPIN 1, 1             #  12: f501
    LDI r2, 18               #  13: 1212
idle_0:
    INBIT r1, 1              #  14: e501
    JZ r1, 12                #  15: 910c
    DJNZ r2, 14              #  16: a20e
    LDI r1, 1                #  17: 1101
    OUTBIT r1, 2             #  18: e102
start:
    WAITPIN 1, 0             #  19: f401
    LDI r1, 0                #  20: 1100
    OUTBIT r1, 2             #  21: e102
    OUTBIT r1, 3             #  22: e103
    WAIT 20                  #  23: 7014
    INBIT r1, 1              #  24: e501
    JZ r1, 27                #  25: 911b
    JMP 55                   #  26: 8037
start_valid:
    LDI r0, 0                #  27: 1000
    LDI r2, 8                #  28: 1208
    WAIT 45                  #  29: 702d
rx_data:
    INBIT r1, 1              #  30: e501
    SHR r0                   #  31: d400
    ROR r1                   #  32: dd00
    OR r0, r1                #  33: b801
    WAIT 44                  #  34: 702c
    DJNZ r2, 30              #  35: a21e
    INBIT r1, 1              #  36: e501
    JZ r1, 62                #  37: 913e
    LDI r3, 0                #  38: 1300
    STORE r0, r3             #  39: 3403
    OUT r0, 1                #  40: 4401
    OUTBIT r1, 3             #  41: e103
    LDI r0, 0                #  42: 1000
    OUTBIT r0, 0             #  43: e000
    LOAD r0, r3              #  44: 2403
    LDI r2, 8                #  45: 1208
    LDI r1, 1                #  46: 1101
    WAIT 44                  #  47: 702c
tx_data:
    OUTBIT r0, 0             #  48: e000
    SHR r0                   #  49: d400
    WAIT 46                  #  50: 702e
    DJNZ r2, 48              #  51: a230
    OUTBIT r1, 0             #  52: e100
    WAIT 47                  #  53: 702f
    JMP 12                   #  54: 800c
false_start:
    LDI r1, 1                #  55: 1101
    OUTBIT r1, 4             #  56: e104
    LDI r2, 241              #  57: 12f1
    LOAD r1, r2              #  58: 2502
    ADDI r1, 1               #  59: c101
    STORE r1, r2             #  60: 3502
    JMP 12                   #  61: 800c
framing_error:
    LDI r1, 1                #  62: 1101
    OUTBIT r1, 5             #  63: e105
    LDI r2, 242              #  64: 12f2
    LOAD r1, r2              #  65: 2502
    ADDI r1, 1               #  66: c101
    STORE r1, r2             #  67: 3502
    JMP 12                   #  68: 800c
