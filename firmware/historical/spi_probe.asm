# SPI mode-0 controller exploration, 100 kHz intrabyte SCLK at 50 MHz.
# uio0=CS_n, 1=SCLK, 2=MOSI, 3=MISO. Valid requests only.
# Arbitrary prebuffered TX bytes (0..64), same number of RX output entries.
# Scratch event 144..159; remaining TX count 160. No protocol-specific RTL.
    SETO 1
    SETOE 7
idle:
    LDI r3, 0x22
    PREAD r0, r3
    JFAIL idle
    LDI r1, 144
    STORE r0, r1
    PREAD r0, r3
    ADDI r1, 1
    STORE r0, r1
    LDI r2, 14
record:
    PREAD r0, r3
    DJNZ r2, record
    LDI r1, 146
    LDI r0, 1
    STORE r0, r1
    ADDI r1, 1
    LDI r2, 13
    LDI r0, 0
clear_event:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, clear_event
    LDI r3, 2
    PREAD r0, r3
    LDI r1, 148
    STORE r0, r1
    LDI r1, 150
    STORE r0, r1
    LDI r1, 160
    STORE r0, r1
    JZ r0, publish
    SETO 0
byte:
    LDI r3, 0x11
    PREAD r0, r3
    LDI r1, 0
    LDI r2, 8
bit:
    ROL r0
    OUTBIT r0, 2
    WAIT 246
    LDI r3, 1
    OUTBIT r3, 1
    WAIT 243
    SHL r1
    INBIT r1, 3
    LDI r3, 0
    OUTBIT r3, 1
    DJNZ r2, bit
    LDI r3, 0x30
    PWRITE r1, r3
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    ADDI r3, 1
    PWRITE r0, r3
    LDI r1, 160
    LOAD r0, r1
    ADDI r0, 255
    STORE r0, r1
    JZ r0, finish
    JMP byte
finish:
    SETO 1
publish:
    LDI r1, 144
    LDI r2, 16
    LDI r3, 0x40
event:
    LOAD r0, r1
    PWRITE r0, r3
    ADDI r1, 1
    DJNZ r2, event
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    JMP idle
